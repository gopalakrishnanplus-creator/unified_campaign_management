import logging
import mimetypes
import os
import re
from contextlib import ExitStack
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import Department, Ticket, TicketAttachment


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

TOKEN_SYNONYMS = {
    "it": "tech",
    "technical": "tech",
    "technology": "tech",
    "technologies": "tech",
    "ops": "operations",
    "operation": "operations",
}


def external_ticketing_enabled():
    return bool(settings.EXTERNAL_TICKETING_BASE_URL and settings.EXTERNAL_TICKETING_SYNC_ENABLED)


def should_sync_external_ticket(ticket):
    return bool(external_ticketing_enabled() and not ticket.external_ticket_number)


def sync_external_directory():
    if not external_ticketing_enabled():
        return []

    directory = fetch_directory_snapshot()
    synced_departments = []
    with transaction.atomic():
        for raw_department in directory.get("departments") or []:
            external_department = enrich_department_with_manager(
                raw_department,
                directory.get("department_managers") or [],
                directory.get("users") or [],
            )
            department = upsert_local_department(external_department)
            synced_departments.append(department)
    return synced_departments


def sync_external_ticket(ticket_id):
    ticket = (
        Ticket.objects.select_related(
            "department",
            "current_assignee",
            "direct_recipient",
            "created_by",
            "submitted_by",
            "ticket_type_definition",
            "support_request",
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
        attachment_sources = get_ticket_attachment_sources(ticket)
        sync_log.append(
            log_line(
                "Creating external ticket.",
                department=payload.get("department") or payload.get("department_id"),
                assigned_to_email=payload.get("assigned_to_email"),
                project_manager_email=payload.get("project_manager_email"),
                ticket_type_id=payload.get("ticket_type_id"),
                ticket_type_other=payload.get("ticket_type_other"),
                priority=payload.get("priority"),
                attachment_count=len(attachment_sources),
            )
        )
        response_payload = send_external_ticket_create_request(payload, attachment_sources)
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


def sync_external_ticket_attachments(ticket_id, *, attachment_ids=None):
    ticket = (
        Ticket.objects.select_related(
            "department",
            "current_assignee",
            "direct_recipient",
            "created_by",
            "submitted_by",
            "support_request",
        )
        .filter(pk=ticket_id)
        .first()
    )
    if not ticket or not external_ticketing_enabled() or not ticket.external_ticket_number:
        return None

    attachment_sources = get_ticket_attachment_sources(
        ticket,
        attachment_ids=attachment_ids,
        include_support_request=False,
    )
    if not attachment_sources:
        return None

    sync_log = [
        log_line(
            "Syncing ticket attachments to external ticket.",
            external_ticket_number=ticket.external_ticket_number,
            attachment_count=len(attachment_sources),
        )
    ]
    try:
        payload = {
            "updated_by_email": resolve_external_update_actor_email(ticket),
            "message": f"{len(attachment_sources)} attachment(s) uploaded from Campaign Management.",
        }
        response_payload = send_external_ticket_update_request(
            ticket,
            payload,
            attachment_sources,
        )
        external_ticket = response_payload.get("ticket") or {}
        sync_log.append(
            log_line(
                "External ticket attachments synced successfully.",
                external_ticket_number=ticket.external_ticket_number,
                status=external_ticket.get("status_code") or external_ticket.get("status"),
            )
        )
        ticket.external_ticket_synced_at = timezone.now()
        ticket.external_ticket_error = ""
        if external_ticket.get("status_code") or external_ticket.get("status"):
            ticket.external_ticket_status = external_ticket.get("status_code") or external_ticket.get("status") or ticket.external_ticket_status
        ticket.external_ticket_log = "\n".join(filter(None, [ticket.external_ticket_log, *sync_log]))
        ticket.save(
            update_fields=[
                "external_ticket_status",
                "external_ticket_synced_at",
                "external_ticket_error",
                "external_ticket_log",
            ]
        )
        logger.info("External ticket attachment sync succeeded for %s\n%s", ticket.ticket_number, "\n".join(sync_log))
        return ticket
    except Exception as exc:
        sync_log.append(log_line("External ticket attachment sync failed.", error=str(exc)))
        ticket.external_ticket_error = str(exc)
        ticket.external_ticket_log = "\n".join(filter(None, [ticket.external_ticket_log, *sync_log]))
        ticket.save(update_fields=["external_ticket_error", "external_ticket_log"])
        logger.warning("External ticket attachment sync failed for %s\n%s", ticket.ticket_number, "\n".join(sync_log))
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


def get_ticket_attachment_sources(ticket, *, attachment_ids=None, include_support_request=True):
    sources = []
    seen = set()
    attachments = TicketAttachment.objects.filter(note__ticket=ticket).order_by("created_at")
    if attachment_ids is not None:
        attachments = attachments.filter(pk__in=list(attachment_ids))

    for attachment in attachments:
        add_attachment_source(sources, seen, attachment.file)

    if include_support_request and ticket.support_request_id and ticket.support_request and ticket.support_request.uploaded_file:
        add_attachment_source(sources, seen, ticket.support_request.uploaded_file)
    return sources


def add_attachment_source(sources, seen, field_file):
    if not field_file:
        return
    filename = os.path.basename(getattr(field_file, "name", "") or "")
    if not filename:
        return
    try:
        size = field_file.size
    except Exception:
        size = None
    key = (filename.lower(), size)
    if key in seen:
        return
    seen.add(key)
    sources.append({"filename": filename, "field_file": field_file})


def send_external_ticket_create_request(payload, attachment_sources):
    if not attachment_sources:
        return api_request("POST", "/client-tickets/api/tickets/", json=payload)
    with AttachmentUploadContext(attachment_sources) as files:
        return api_request("POST", "/client-tickets/api/tickets/", data=payload, files=files)


def send_external_ticket_update_request(ticket, payload, attachment_sources):
    if not attachment_sources:
        return api_request(
            "POST",
            f"/client-tickets/api/tickets/{ticket.external_ticket_number}/inditech-update/",
            json=payload,
        )
    with AttachmentUploadContext(attachment_sources) as files:
        return api_request(
            "POST",
            f"/client-tickets/api/tickets/{ticket.external_ticket_number}/inditech-update/",
            data=payload,
            files=files,
        )


class AttachmentUploadContext:
    def __init__(self, attachment_sources):
        self.attachment_sources = attachment_sources
        self.stack = ExitStack()
        self.files = []

    def __enter__(self):
        for source in self.attachment_sources:
            field_file = source["field_file"]
            self.stack.callback(field_file.close)
            field_file.open("rb")
            content_type = mimetypes.guess_type(source["filename"])[0] or "application/octet-stream"
            self.files.append(
                (
                    "attachments",
                    (
                        source["filename"],
                        field_file.file,
                        content_type,
                    ),
                )
            )
        return self.files

    def __exit__(self, exc_type, exc, tb):
        self.stack.close()
        return False


def resolve_requester_number(ticket):
    if ticket.requester_number:
        return ticket.requester_number
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


def resolve_external_update_actor_email(ticket):
    for user in (ticket.current_assignee, ticket.direct_recipient, ticket.created_by, ticket.submitted_by):
        if user and user.email:
            return user.email
    return resolve_project_manager_email(ticket)


def resolve_department_manager_email(ticket, external_department):
    manager_email = (external_department.get("manager_email") or "").strip()
    if manager_email:
        return manager_email
    raise ExternalTicketingSyncError(
        f"No external department manager mapping was found for local department {ticket.department.name}."
    )


def resolve_external_department(ticket):
    if ticket.department_id and (not ticket.department.external_directory_id or not ticket.department.default_recipient_id):
        try:
            sync_external_directory()
            ticket.refresh_from_db()
        except ExternalTicketingSyncError:
            pass

    directory = fetch_directory_snapshot()
    departments = directory.get("departments") or []
    managers = directory.get("department_managers") or []
    users = directory.get("users") or []

    target_names = {normalize_value(ticket.department.name)}
    target_codes = {normalize_value(ticket.department.code)}
    if ticket.department.external_directory_name:
        target_names.add(normalize_value(ticket.department.external_directory_name))
    if ticket.department.external_directory_code:
        target_codes.add(normalize_value(ticket.department.external_directory_code))

    if ticket.department.external_directory_id:
        for department in departments:
            if department.get("id") == ticket.department.external_directory_id:
                return enrich_department_with_manager(department, managers, users)

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

    fuzzy_match = find_best_department_match(target_names, target_codes, departments, managers, users)
    if fuzzy_match:
        return fuzzy_match

    raise ExternalTicketingSyncError(
        f"Could not match local department {ticket.department.display_name} ({ticket.department.display_code}) in the internal ticketing directory."
    )


def fetch_directory_snapshot():
    directory = {
        "departments": [],
        "department_managers": [],
        "users": [],
    }

    department_lookup_error = None
    try:
        departments_payload = fetch_external_departments()
    except ExternalTicketingSyncError as exc:
        departments_payload = {}
        department_lookup_error = exc
    directory["departments"] = departments_payload.get("departments") or []

    try:
        system_directory = fetch_system_directory()
    except ExternalTicketingSyncError as exc:
        system_directory = {}
        if not directory["departments"]:
            raise department_lookup_error or exc

    if system_directory.get("departments"):
        directory["departments"] = merge_department_records(directory["departments"], system_directory.get("departments") or [])
    directory["department_managers"] = system_directory.get("department_managers") or []
    directory["users"] = system_directory.get("users") or []
    if not directory["departments"] and department_lookup_error:
        raise department_lookup_error
    return directory


def fetch_system_directory():
    return api_request("GET", "/client-tickets/api/lookups/system-directory/")


def fetch_external_departments():
    return api_request("GET", "/client-tickets/api/lookups/departments/")


def upsert_local_department(external_department):
    department = find_local_department_for_external(external_department)
    manager_user = upsert_external_manager_user(external_department)
    support_email = determine_support_email(external_department, department=department, manager_user=manager_user)

    defaults = {
        "name": department.name if department else external_department.get("name") or "External Department",
        "code": department.code if department else trim_department_code(external_department.get("code"), external_department.get("id")),
        "description": department.description if department else "",
        "support_email": support_email,
        "default_recipient": manager_user,
        "external_directory_name": external_department.get("name") or "",
        "external_directory_code": external_department.get("code") or "",
        "external_manager_email": external_department.get("manager_email") or "",
        "is_active": bool(external_department.get("is_active", True)),
    }

    if department:
        for field, value in defaults.items():
            setattr(department, field, value)
    else:
        department = Department(**defaults)

    department.external_directory_id = external_department.get("id")
    department.save()
    return department


def find_local_department_for_external(external_department):
    external_id = external_department.get("id")
    external_code = normalize_value(external_department.get("code"))
    external_name = normalize_value(external_department.get("name"))

    if external_id:
        department = Department.objects.filter(external_directory_id=external_id).first()
        if department:
            return department
    if external_code:
        department = Department.objects.filter(external_directory_code__iexact=external_department.get("code")).first()
        if department:
            return department
        department = Department.objects.filter(code__iexact=external_department.get("code")).first()
        if department:
            return department
    if external_name:
        department = Department.objects.filter(external_directory_name__iexact=external_department.get("name")).first()
        if department:
            return department
        department = Department.objects.filter(name__iexact=external_department.get("name")).first()
        if department:
            return department

    target_tokens = tokenize_department_value(external_department.get("name")) | tokenize_department_value(
        external_department.get("code")
    )
    best_score = 0
    best_department = None
    for department in Department.objects.all():
        candidate_tokens = (
            tokenize_department_value(department.name)
            | tokenize_department_value(department.code)
            | tokenize_department_value(department.external_directory_name)
            | tokenize_department_value(department.external_directory_code)
        )
        score = len(target_tokens & candidate_tokens)
        if score > best_score:
            best_score = score
            best_department = department
    if best_score >= 2:
        return best_department
    return None


def upsert_external_manager_user(external_department):
    manager_email = (external_department.get("manager_email") or "").strip().lower()
    if not manager_email:
        return None
    manager_name = (external_department.get("manager_name") or manager_email).strip()
    user, _ = User.objects.update_or_create(
        email=manager_email,
        defaults={
            "full_name": manager_name,
            "role": User.Role.DEPARTMENT_OWNER,
            "is_staff": True,
            "company": "Inditech",
        },
    )
    return user


def determine_support_email(external_department, *, department=None, manager_user=None):
    manager_email = (external_department.get("manager_email") or "").strip().lower()
    if department and department.support_email:
        if not manager_email or manager_email == department.support_email.lower():
            return department.support_email
    if manager_email and not Department.objects.exclude(pk=getattr(department, "pk", None)).filter(support_email__iexact=manager_email).exists():
        return manager_email
    code = external_department.get("code") or external_department.get("name") or f"department-{external_department.get('id')}"
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_value(code)).strip("-") or f"department-{external_department.get('id')}"
    fallback = f"{slug}@inditech.local"
    if Department.objects.exclude(pk=getattr(department, "pk", None)).filter(support_email__iexact=fallback).exists():
        fallback = f"{slug}-{external_department.get('id')}@inditech.local"
    return fallback


def trim_department_code(code, external_id):
    code = re.sub(r"[^A-Z0-9_-]+", "", str(code or "").upper())[:24]
    if code:
        return code
    return f"EXT-{external_id}"[:24]


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


def merge_department_records(primary_departments, secondary_departments):
    merged = []
    seen = set()
    for department in [*(primary_departments or []), *(secondary_departments or [])]:
        key = department.get("id") or (
            normalize_value(department.get("code")),
            normalize_value(department.get("name")),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(department)
    return merged


def find_best_department_match(target_names, target_codes, departments, managers, users):
    target_tokens = set()
    for value in [*target_names, *target_codes]:
        target_tokens.update(tokenize_department_value(value))
    if not target_tokens:
        return None

    best_score = 0
    best_match = None
    for department in departments:
        candidate_tokens = tokenize_department_value(department.get("name")) | tokenize_department_value(department.get("code"))
        score = len(target_tokens & candidate_tokens)
        if score > best_score:
            best_score = score
            best_match = enrich_department_with_manager(department, managers, users)

    if best_score >= 2:
        return best_match

    return None


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


def api_request(method, path, *, params=None, json=None, data=None, files=None):
    url = build_api_url(path)
    request_kwargs = {
        "headers": build_headers(),
        "params": params,
        "timeout": settings.EXTERNAL_TICKETING_TIMEOUT,
    }
    if json is not None:
        request_kwargs["json"] = json
    if data is not None:
        request_kwargs["data"] = data
    if files is not None:
        request_kwargs["files"] = files
    response = requests.request(method, url, **request_kwargs)
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


def tokenize_department_value(value):
    normalized = normalize_value(value)
    if not normalized:
        return set()
    tokens = {
        TOKEN_SYNONYMS.get(token, token)
        for token in re.split(r"[^a-z0-9]+", normalized)
        if token
    }
    return tokens
