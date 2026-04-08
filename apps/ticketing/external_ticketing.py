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
    return bool(external_ticketing_enabled() and not ticket.external_ticket_number)


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

    sync_log = [log_line("Starting external ticket sync.")]
    try:
        sync_log.append(
            log_line(
                "Checking for an existing external ticket.",
                external_reference=ticket.ticket_number,
                source_system=settings.EXTERNAL_TICKETING_SOURCE_SYSTEM,
            )
        )
        existing_ticket = find_external_ticket_by_reference(ticket)
        if existing_ticket:
            sync_log.append(
                log_line(
                    "Existing external ticket found.",
                    external_ticket_number=existing_ticket.get("ticket_number"),
                    status=existing_ticket.get("status_code") or existing_ticket.get("status"),
                )
            )
            return persist_external_ticket_mapping(ticket, existing_ticket, sync_log)

        payload = build_external_ticket_payload(ticket)
        sync_log.append(
            log_line(
                "Creating external ticket.",
                department=payload.get("department") or payload.get("department_id"),
                assigned_to_email=payload.get("assigned_to_email"),
                project_manager_email=payload.get("project_manager_email"),
                ticket_type_id=payload.get("ticket_type_id"),
                ticket_type_other=payload.get("ticket_type_other"),
                priority=payload.get("priority"),
            )
        )
        response_payload = api_request("POST", "/client-tickets/api/tickets/", json=payload)
        external_ticket = response_payload.get("ticket") or {}
        if not response_payload.get("success") or not external_ticket.get("ticket_number"):
            raise ExternalTicketingSyncError(
                response_payload.get("error") or "External ticketing API did not return a ticket number."
            )
        sync_log.append(
            log_line(
                "External ticket created successfully.",
                external_ticket_number=external_ticket.get("ticket_number"),
                status=external_ticket.get("status_code") or external_ticket.get("status"),
                external_ticket_url=external_ticket.get("ticket_url"),
            )
        )
        return persist_external_ticket_mapping(ticket, external_ticket, sync_log)
    except Exception as exc:
        ticket.external_ticket_error = str(exc)
        sync_log.append(log_line("External ticket sync failed.", error=str(exc)))
        ticket.external_ticket_log = "\n".join(sync_log)
        ticket.save(update_fields=["external_ticket_error", "external_ticket_log"])
        logger.warning("External ticket sync failed for %s\n%s", ticket.ticket_number, ticket.external_ticket_log)
        return None


def persist_external_ticket_mapping(ticket, external_ticket, sync_log=None):
    ticket.external_ticket_number = external_ticket.get("ticket_number", "") or ticket.external_ticket_number
    ticket.external_ticket_url = external_ticket.get("ticket_url", "") or ticket.external_ticket_url
    ticket.external_ticket_status = (
        external_ticket.get("status_code", "") or external_ticket.get("status", "") or ticket.external_ticket_status
    )
    ticket.external_ticket_synced_at = timezone.now()
    ticket.external_ticket_error = ""
    if sync_log:
        ticket.external_ticket_log = "\n".join(sync_log)
    ticket.save(
        update_fields=[
            "external_ticket_number",
            "external_ticket_url",
            "external_ticket_status",
            "external_ticket_synced_at",
            "external_ticket_error",
            "external_ticket_log",
        ]
    )
    if ticket.external_ticket_log:
        logger.info("External ticket sync succeeded for %s\n%s", ticket.ticket_number, ticket.external_ticket_log)
    return ticket


def build_external_ticket_payload(ticket):
    external_department = resolve_external_department(ticket)
    external_ticket_type_id = resolve_external_ticket_type_id(ticket, department_id=external_department.get("id"))
    payload = {
        "title": ticket.title,
        "description": ticket.description,
        "requester_name": ticket.requester_name,
        "requester_email": ticket.requester_email,
        "requester_number": resolve_requester_number(ticket),
        "assigned_to_email": resolve_department_manager_email(ticket, external_department),
        "project_manager_email": resolve_project_manager_email(ticket),
        "user_type": USER_TYPE_MAP.get(ticket.user_type, "client"),
        "source_system": settings.EXTERNAL_TICKETING_SOURCE_SYSTEM,
        "priority": PRIORITY_MAP.get(ticket.priority, "medium"),
        "status": STATUS_MAP.get(ticket.status, "open"),
        "external_reference": ticket.ticket_number,
    }
    if external_department.get("id"):
        payload["department_id"] = external_department["id"]
    else:
        payload["department"] = external_department["name"]
    if external_ticket_type_id:
        payload["ticket_type_id"] = external_ticket_type_id
    elif ticket.ticket_type:
        payload["ticket_type_other"] = ticket.ticket_type
    return payload


def resolve_requester_number(ticket):
    if ticket.requester_email:
        requester_user = User.objects.filter(email__iexact=ticket.requester_email).exclude(phone_number="").first()
        if requester_user and requester_user.phone_number:
            return requester_user.phone_number
    for user in (ticket.created_by, ticket.submitted_by):
        if user and user.phone_number:
            return user.phone_number
    if settings.EXTERNAL_TICKETING_REQUESTER_PHONE_FALLBACK:
        return settings.EXTERNAL_TICKETING_REQUESTER_PHONE_FALLBACK
    raise ExternalTicketingSyncError(
        "Requester phone number is required for external ticket sync. "
        "Populate the requester/creator phone number or set EXTERNAL_TICKETING_REQUESTER_PHONE_FALLBACK."
    )


def resolve_project_manager_email(ticket):
    for user in (ticket.created_by, ticket.submitted_by):
        if user and user.is_project_manager and user.email:
            return user.email
    if settings.PROJECT_MANAGER_EMAIL:
        return settings.PROJECT_MANAGER_EMAIL
    raise ExternalTicketingSyncError("External ticket sync requires a valid project manager email.")


def resolve_department_manager_email(ticket, external_department):
    manager_email = (external_department.get("manager_email") or "").strip()
    if manager_email:
        return manager_email
    raise ExternalTicketingSyncError(
        f"No external department manager mapping was found for local department {ticket.department.name}."
    )


def resolve_external_department(ticket):
    directory = api_request("GET", "/client-tickets/api/lookups/system-directory/")
    departments = directory.get("departments") or []
    managers = directory.get("department_managers") or []
    users = directory.get("users") or []

    target_names = {normalize_value(ticket.department.name)}
    target_codes = {normalize_value(ticket.department.code)}
    for mapped_value in configured_department_aliases(ticket.department):
        normalized = normalize_value(mapped_value)
        if normalized:
            target_names.add(normalized)
            target_codes.add(normalized)

    for department in departments:
        if normalize_value(department.get("name")) in target_names:
            return enrich_department_with_manager(department, managers, users)
        if normalize_value(department.get("code")) in target_codes:
            return enrich_department_with_manager(department, managers, users)

    for manager in managers:
        if normalize_value(manager.get("department_name")) in target_names:
            return enrich_department_with_manager(
                {
                    "id": manager.get("department_id"),
                    "name": manager.get("department_name"),
                    "code": manager.get("department_code"),
                },
                managers,
                users,
            )
        if normalize_value(manager.get("department_code")) in target_codes:
            return enrich_department_with_manager(
                {
                    "id": manager.get("department_id"),
                    "name": manager.get("department_name"),
                    "code": manager.get("department_code"),
                },
                managers,
                users,
            )

    raise ExternalTicketingSyncError(
        f"Could not match local department {ticket.department.name} ({ticket.department.code}) in the external system directory."
    )


def enrich_department_with_manager(department, managers, users):
    enriched = {
        "id": department.get("id"),
        "name": department.get("name"),
        "code": department.get("code"),
        "manager_id": department.get("manager_id"),
        "manager_name": department.get("manager_name"),
        "manager_email": department.get("manager_email"),
    }
    if enriched.get("manager_email"):
        return enriched

    manager_record = find_department_manager_record(enriched, managers)
    if manager_record:
        enriched["manager_id"] = manager_record.get("manager_id") or enriched.get("manager_id")
        enriched["manager_name"] = manager_record.get("manager_name") or enriched.get("manager_name")
        enriched["manager_email"] = manager_record.get("manager_email") or enriched.get("manager_email")

    if enriched.get("manager_email"):
        return enriched

    manager_id = enriched.get("manager_id")
    if manager_id:
        user_record = next((user for user in users if user.get("id") == manager_id), None)
        if user_record:
            enriched["manager_name"] = user_record.get("full_name") or enriched.get("manager_name")
            enriched["manager_email"] = user_record.get("email") or enriched.get("manager_email")
    return enriched


def find_department_manager_record(department, managers):
    department_id = department.get("id")
    department_name = normalize_value(department.get("name"))
    department_code = normalize_value(department.get("code"))
    for manager in managers:
        if department_id and manager.get("department_id") == department_id:
            return manager
        if department_name and normalize_value(manager.get("department_name")) == department_name:
            return manager
        if department_code and normalize_value(manager.get("department_code")) == department_code:
            return manager
    return None


def configured_department_aliases(department):
    mapping = settings.EXTERNAL_TICKETING_DEPARTMENT_MAP or {}
    aliases = []
    for key in (department.code, department.name):
        value = mapping.get(key)
        if isinstance(value, str):
            aliases.append(value)
        elif isinstance(value, (list, tuple)):
            aliases.extend(value)
        elif isinstance(value, dict):
            aliases.extend([value.get("name"), value.get("code")])
    return [alias for alias in aliases if alias]


def resolve_external_ticket_type_id(ticket, *, department_id=None):
    params = {"is_active": "true"}
    if department_id:
        params["department_id"] = department_id
    response_payload = api_request("GET", "/client-tickets/api/lookups/ticket-types/", params=params)
    local_type = normalize_value(ticket.ticket_type)
    for ticket_type in response_payload.get("ticket_types") or []:
        if normalize_value(ticket_type.get("name")) == local_type:
            return ticket_type.get("id")
    if department_id:
        response_payload = api_request("GET", "/client-tickets/api/lookups/ticket-types/", params={"is_active": "true"})
        for ticket_type in response_payload.get("ticket_types") or []:
            if normalize_value(ticket_type.get("name")) == local_type:
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
            data.get("error") or data.get("message") or f"{method} {url} failed with status {response.status_code}."
        )
    return data


def normalize_value(value):
    return str(value or "").strip().lower()


def log_line(message, **context):
    safe_context = {key: value for key, value in context.items() if value not in (None, "", [], {}, ())}
    if not safe_context:
        return f"[{timezone.now().strftime('%d %b %Y %H:%M:%S')}] {message}"
    context_blob = ", ".join(f"{key}={value}" for key, value in safe_context.items())
    return f"[{timezone.now().strftime('%d %b %Y %H:%M:%S')}] {message} {context_blob}"
