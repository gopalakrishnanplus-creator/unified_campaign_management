import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import User

from .models import Ticket


logger = logging.getLogger(__name__)


class ExternalTicketingSyncError(Exception):
    pass


PRIORITY_MAP = {
    Ticket.Priority.LOW: "low",
    Ticket.Priority.MEDIUM: "medium",
    Ticket.Priority.HIGH: "high",
    Ticket.Priority.CRITICAL: "urgent",
}

STATUS_MAP = {
    Ticket.Status.NOT_STARTED: "open",
    Ticket.Status.IN_PROCESS: "in_progress",
    Ticket.Status.ON_HOLD: "waiting_for_inditech",
    Ticket.Status.CANNOT_COMPLETE: "cancelled",
    Ticket.Status.COMPLETED: "closed",
}

USER_TYPE_MAP = {
    Ticket.UserType.INTERNAL: "internal",
    Ticket.UserType.DOCTOR: "client",
    Ticket.UserType.CLINIC_STAFF: "client",
    Ticket.UserType.BRAND_MANAGER: "client",
    Ticket.UserType.FIELD_REP: "client",
    Ticket.UserType.PATIENT: "client",
}


def external_ticketing_enabled():
    return bool(settings.EXTERNAL_TICKETING_SYNC_ENABLED and settings.EXTERNAL_TICKETING_BASE_URL)


def should_sync_external_ticket(ticket):
    if not external_ticketing_enabled() or ticket.external_ticket_number:
        return False
    creator = ticket.created_by or ticket.submitted_by
    return bool(creator and creator.is_project_manager)


def sync_external_ticket(ticket_id):
    ticket = (
        Ticket.objects.select_related(
            "department",
            "current_assignee",
            "direct_recipient",
            "created_by",
            "submitted_by",
            "ticket_type_definition",
        )
        .filter(pk=ticket_id)
        .first()
    )
    if not ticket or not should_sync_external_ticket(ticket):
        return None

    try:
        existing_ticket = find_external_ticket_by_reference(ticket)
        if existing_ticket:
            return persist_external_ticket_mapping(ticket, existing_ticket)

        payload = build_external_ticket_payload(ticket)
        response_payload = api_request("POST", "/client-tickets/api/tickets/", json=payload)
        external_ticket = response_payload.get("ticket") or {}
        if not response_payload.get("success") or not external_ticket.get("ticket_number"):
            raise ExternalTicketingSyncError(response_payload.get("error") or "External ticketing API did not return a ticket number.")
        return persist_external_ticket_mapping(ticket, external_ticket)
    except Exception as exc:
        ticket.external_ticket_error = str(exc)
        ticket.save(update_fields=["external_ticket_error"])
        logger.warning("External ticket sync failed for %s: %s", ticket.ticket_number, exc)
        return None


def persist_external_ticket_mapping(ticket, external_ticket):
    ticket.external_ticket_number = external_ticket.get("ticket_number", "") or ticket.external_ticket_number
    ticket.external_ticket_url = external_ticket.get("ticket_url", "") or ticket.external_ticket_url
    ticket.external_ticket_status = external_ticket.get("status_code", "") or external_ticket.get("status", "") or ticket.external_ticket_status
    ticket.external_ticket_synced_at = timezone.now()
    ticket.external_ticket_error = ""
    ticket.save(
        update_fields=[
            "external_ticket_number",
            "external_ticket_url",
            "external_ticket_status",
            "external_ticket_synced_at",
            "external_ticket_error",
        ]
    )
    return ticket


def build_external_ticket_payload(ticket):
    department_id = resolve_external_department_id(ticket)
    ticket_type_id = resolve_external_ticket_type_id(ticket, department_id=department_id)
    payload = {
        "title": ticket.title,
        "description": ticket.description,
        "requester_name": ticket.requester_name,
        "requester_email": ticket.requester_email,
        "requester_number": resolve_requester_number(ticket),
        "assigned_to_email": resolve_assignee_email(ticket),
        "project_manager_email": resolve_project_manager_email(ticket),
        "user_type": USER_TYPE_MAP.get(ticket.user_type, "client"),
        "source_system": settings.EXTERNAL_TICKETING_SOURCE_SYSTEM,
        "priority": PRIORITY_MAP.get(ticket.priority, "medium"),
        "status": STATUS_MAP.get(ticket.status, "open"),
        "external_reference": ticket.ticket_number,
    }
    if department_id:
        payload["department_id"] = department_id
    else:
        payload["department"] = ticket.department.name
    if ticket_type_id:
        payload["ticket_type_id"] = ticket_type_id
    elif ticket.ticket_type:
        payload["ticket_type_other"] = ticket.ticket_type
    return payload


def resolve_requester_number(ticket):
    candidates = []
    if ticket.requester_email:
        candidates.extend(User.objects.filter(email__iexact=ticket.requester_email).exclude(phone_number="")[:1])
    for user in (ticket.created_by, ticket.submitted_by):
        if user and user.phone_number:
            candidates.append(user)
    for user in candidates:
        if user and user.phone_number:
            return user.phone_number
    if settings.EXTERNAL_TICKETING_REQUESTER_PHONE_FALLBACK:
        return settings.EXTERNAL_TICKETING_REQUESTER_PHONE_FALLBACK
    raise ExternalTicketingSyncError(
        "Requester phone number is required for external ticket sync. "
        "Populate the PM/requester phone number or set EXTERNAL_TICKETING_REQUESTER_PHONE_FALLBACK."
    )


def resolve_assignee_email(ticket):
    assignee = ticket.current_assignee or ticket.direct_recipient
    if assignee and assignee.email:
        return assignee.email
    raise ExternalTicketingSyncError("External ticket sync requires a valid assignee email.")


def resolve_project_manager_email(ticket):
    for user in (ticket.created_by, ticket.submitted_by):
        if user and user.is_project_manager and user.email:
            return user.email
    if settings.PROJECT_MANAGER_EMAIL:
        return settings.PROJECT_MANAGER_EMAIL
    raise ExternalTicketingSyncError("External ticket sync requires a valid project manager email.")


def resolve_external_department_id(ticket):
    response_payload = api_request("GET", "/client-tickets/api/lookups/departments/")
    departments = response_payload.get("departments") or []
    ticket_department_name = (ticket.department.name or "").strip().lower()
    ticket_department_code = (ticket.department.code or "").strip().lower()
    for department in departments:
        if (department.get("name") or "").strip().lower() == ticket_department_name:
            return department.get("id")
        if (department.get("code") or "").strip().lower() == ticket_department_code:
            return department.get("id")
    return None


def resolve_external_ticket_type_id(ticket, *, department_id=None):
    params = {"is_active": "true"}
    if department_id:
        params["department_id"] = department_id
    response_payload = api_request("GET", "/client-tickets/api/lookups/ticket-types/", params=params)
    ticket_types = response_payload.get("ticket_types") or []
    local_type = (ticket.ticket_type or "").strip().lower()
    for ticket_type in ticket_types:
        if (ticket_type.get("name") or "").strip().lower() == local_type:
            return ticket_type.get("id")
    if department_id:
        response_payload = api_request("GET", "/client-tickets/api/lookups/ticket-types/", params={"is_active": "true"})
        for ticket_type in response_payload.get("ticket_types") or []:
            if (ticket_type.get("name") or "").strip().lower() == local_type:
                return ticket_type.get("id")
    return None


def find_external_ticket_by_reference(ticket):
    url = build_api_url("/client-tickets/api/tickets/by-external-reference/")
    response = requests.get(
        url,
        headers=build_headers(),
        params={
            "external_reference": ticket.ticket_number,
            "source_system": settings.EXTERNAL_TICKETING_SOURCE_SYSTEM,
        },
        timeout=settings.EXTERNAL_TICKETING_TIMEOUT,
    )
    if response.status_code == 404:
        return None
    data = parse_json_response(response, "GET", url)
    if not data.get("success"):
        return None
    return data.get("ticket")


def api_request(method, path, *, params=None, json=None):
    url = build_api_url(path)
    response = requests.request(
        method,
        url,
        headers=build_headers(),
        params=params,
        json=json,
        timeout=settings.EXTERNAL_TICKETING_TIMEOUT,
    )
    data = parse_json_response(response, method, url)
    if data.get("success") is False:
        raise ExternalTicketingSyncError(
            data.get("error")
            or data.get("message")
            or f"{method} {url} returned an unsuccessful response."
        )
    return data


def build_api_url(path):
    base_url = settings.EXTERNAL_TICKETING_BASE_URL.rstrip("/") + "/"
    return urljoin(base_url, path.lstrip("/"))


def build_headers():
    headers = {"Accept": "application/json"}
    if settings.EXTERNAL_TICKETING_API_TOKEN:
        headers["X-Client-Ticket-Token"] = settings.EXTERNAL_TICKETING_API_TOKEN
    return headers


def parse_json_response(response, method, url):
    try:
        data = response.json()
    except ValueError as exc:
        raise ExternalTicketingSyncError(f"{method} {url} returned a non-JSON response.") from exc
    if response.status_code >= 400:
        raise ExternalTicketingSyncError(
            data.get("error")
            or data.get("message")
            or f"{method} {url} failed with status {response.status_code}."
        )
    return data
