from datetime import timezone as dt_timezone
from urllib.parse import quote, urljoin, urlparse

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import Truncator

from apps.accounts.models import User
from apps.campaigns.models import Campaign

from .models import Department, SpecialInstructionReview, Ticket, TicketRoutingEvent
from .services import create_ticket, get_or_create_ticket_category, get_or_create_ticket_type_definition


class SpecialInstructionAPIError(Exception):
    pass


def fetch_special_instruction_ticket_payload(*, doctor_id, campaign_id=None):
    doctor_id = str(doctor_id or "").strip()
    if not doctor_id:
        raise SpecialInstructionAPIError("Doctor ID is required.")
    params = {}
    if campaign_id:
        params["campaign_id"] = str(campaign_id).strip()
    return special_instruction_api_request(
        "GET",
        f"/internal/special-instructions/{quote(doctor_id)}/ticket/",
        params=params,
    )


def approve_special_instruction_review(review, actor):
    try:
        response_payload = special_instruction_api_request("POST", review.approve_url or _approve_path(review.doctor_id))
    except Exception as exc:
        review.approve_error = str(exc)
        review.save(update_fields=["approve_error", "updated_at"])
        raise

    now = timezone.now()
    review.approved_at = now
    review.approved_by = actor if getattr(actor, "is_authenticated", False) else None
    review.approve_response = response_payload or {}
    review.approve_error = ""
    review.rfa_current_status = _extract_status_label(response_payload) or "Document uploaded"
    review.rfa_status_code = _extract_status_code(response_payload) or "uploaded"
    review.save(
        update_fields=[
            "approved_at",
            "approved_by",
            "approve_response",
            "approve_error",
            "rfa_current_status",
            "rfa_status_code",
            "updated_at",
        ]
    )

    ticket = review.ticket
    if ticket.status != Ticket.Status.COMPLETED:
        old_status = ticket.get_status_display()
        ticket.status = Ticket.Status.COMPLETED
        ticket.save(update_fields=["status", "resolved_at", "updated_at"])
        TicketRoutingEvent.objects.create(
            ticket=ticket,
            action=TicketRoutingEvent.Action.STATUS_CHANGED,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            from_user=ticket.current_assignee,
            to_user=ticket.current_assignee,
            description=f"Special Instruction approved; status changed from {old_status} to {ticket.get_status_display()}.",
        )
    return response_payload


def download_special_instruction_document(review):
    response = raw_special_instruction_request("GET", review.download_url or _download_path(review.doctor_id), stream=True)
    if response.status_code >= 400:
        raise SpecialInstructionAPIError(_response_error_message(response, "GET", getattr(response, "url", "")))
    return response


@transaction.atomic
def create_or_update_special_instruction_review(payload, *, actor=None):
    ticket_payload = (payload or {}).get("ticket") or {}
    doctor = ticket_payload.get("doctor") or {}
    clinic = ticket_payload.get("clinic") or {}
    campaign_payload = ticket_payload.get("associated_campaign") or {}
    instruction = ticket_payload.get("special_instruction") or {}
    assigned_field_rep = ticket_payload.get("assigned_field_rep") or {}
    campaign_field_rep = campaign_payload.get("field_rep") or {}

    doctor_id = str(doctor.get("id") or "").strip()
    if not doctor_id:
        raise SpecialInstructionAPIError("RFA ticket payload did not include doctor.id.")
    source_reference = build_special_instruction_source_reference(doctor_id, campaign_payload.get("campaign_id"))
    pm_user = resolve_project_manager_user(actor)
    department = resolve_special_instruction_review_department()
    local_campaign = resolve_local_campaign(campaign_payload)
    review = (
        SpecialInstructionReview.objects.select_related("ticket")
        .filter(source_reference=source_reference)
        .first()
    )

    title = build_special_instruction_ticket_title(doctor, campaign_payload)
    description = build_special_instruction_ticket_description(
        doctor=doctor,
        clinic=clinic,
        campaign=campaign_payload,
        campaign_field_rep=campaign_field_rep,
        assigned_field_rep=assigned_field_rep,
        instruction=instruction,
    )
    if review:
        ticket = review.ticket
        update_existing_special_instruction_ticket(ticket, title, description, local_campaign, doctor, clinic)
    else:
        category = get_or_create_ticket_category(
            "Content",
            description="Issues with content accuracy, freshness, or asset updates.",
            display_order=8,
        )
        ticket_type = get_or_create_ticket_type_definition(
            category=category,
            name="Special Instruction Approval",
            description="Review and approval workflow for RFA Special Instruction documents.",
            department=department,
            source_system=Ticket.SourceSystem.RED_FLAG_ALERT,
            default_priority=Ticket.Priority.HIGH,
        )
        ticket = create_ticket(
            title=title,
            description=description,
            ticket_category=category,
            ticket_type_definition=ticket_type,
            user_type=Ticket.UserType.DOCTOR,
            source_system=Ticket.SourceSystem.RED_FLAG_ALERT,
            priority=Ticket.Priority.HIGH,
            status=Ticket.Status.NOT_STARTED,
            department=department,
            campaign=local_campaign,
            created_by=pm_user,
            submitted_by=pm_user,
            direct_recipient=pm_user,
            current_assignee=pm_user,
            requester_name=doctor.get("name") or doctor_id,
            requester_email=doctor.get("email") or pm_user.email,
            requester_number=clinic.get("phone") or "",
            requester_company=clinic.get("name") or "",
            sync_external=False,
        )

    review_values = build_special_instruction_review_values(
        ticket=ticket,
        source_reference=source_reference,
        payload=payload,
        doctor=doctor,
        clinic=clinic,
        campaign=campaign_payload,
        campaign_field_rep=campaign_field_rep,
        assigned_field_rep=assigned_field_rep,
        instruction=instruction,
    )
    if review:
        for field, value in review_values.items():
            setattr(review, field, value)
        review.save(update_fields=[*review_values.keys(), "updated_at"])
    else:
        review = SpecialInstructionReview.objects.create(**review_values)
    return review


def special_instruction_api_request(method, path_or_url, *, params=None, json=None, data=None):
    response = raw_special_instruction_request(method, path_or_url, params=params, json=json, data=data)
    try:
        response_payload = response.json()
    except ValueError as exc:
        raise SpecialInstructionAPIError(f"{method} {getattr(response, 'url', '')} returned a non-JSON response.") from exc
    if response.status_code >= 400:
        raise SpecialInstructionAPIError(_json_error_message(response_payload, method, getattr(response, "url", ""), response.status_code))
    if response_payload.get("ok") is False or response_payload.get("success") is False:
        raise SpecialInstructionAPIError(
            response_payload.get("error")
            or response_payload.get("message")
            or f"{method} {getattr(response, 'url', '')} returned an unsuccessful response."
        )
    return response_payload


def raw_special_instruction_request(method, path_or_url, *, params=None, json=None, data=None, stream=False):
    url = build_special_instruction_url(path_or_url)
    try:
        return requests.request(
            method,
            url,
            headers=build_special_instruction_headers(),
            params=params,
            json=json,
            data=data,
            stream=stream,
            timeout=settings.SPECIAL_INSTRUCTION_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise SpecialInstructionAPIError(f"{method} {url} could not be reached: {exc}") from exc


def build_special_instruction_headers():
    headers = {"Accept": "application/json"}
    if settings.SPECIAL_INSTRUCTION_PM_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.SPECIAL_INSTRUCTION_PM_API_TOKEN}"
    return headers


def build_special_instruction_url(path_or_url):
    cleaned = clean_payload_url(path_or_url)
    if not cleaned:
        raise SpecialInstructionAPIError("Special Instruction API URL is missing.")
    if cleaned.startswith(("http://", "https://")):
        configured = urlparse(settings.SPECIAL_INSTRUCTION_BASE_URL)
        candidate = urlparse(cleaned)
        if configured.netloc and candidate.netloc != configured.netloc:
            raise SpecialInstructionAPIError("Special Instruction URL host does not match the configured RFA host.")
        return cleaned
    base_url = settings.SPECIAL_INSTRUCTION_BASE_URL.rstrip("/") + "/"
    return urljoin(base_url, cleaned.lstrip("/"))


def clean_payload_url(value):
    return str(value or "").strip().strip("<>").strip()


def build_special_instruction_source_reference(doctor_id, campaign_id=None):
    return f"{doctor_id}:{campaign_id or ''}"


def build_special_instruction_ticket_title(doctor, campaign):
    doctor_label = doctor.get("name") or doctor.get("id") or "Doctor"
    campaign_label = campaign.get("campaign_name") or campaign.get("brand_name") or "RFA campaign"
    return Truncator(f"Special Instruction approval - {doctor_label} / {campaign_label}").chars(255)


def build_special_instruction_ticket_description(*, doctor, clinic, campaign, campaign_field_rep, assigned_field_rep, instruction):
    lines = [
        "RFA Special Instruction approval request",
        "",
        f"Doctor ID: {doctor.get('id') or 'Not provided'}",
        f"Doctor name: {doctor.get('name') or 'Not provided'}",
        f"Doctor email: {doctor.get('email') or 'Not provided'}",
        f"Clinic name: {clinic.get('name') or 'Not provided'}",
        f"Clinic phone: {clinic.get('phone') or 'Not provided'}",
        f"Campaign ID: {campaign.get('campaign_id') or 'Not provided'}",
        f"Campaign name: {campaign.get('campaign_name') or 'Not provided'}",
        f"Brand: {campaign.get('brand_name') or 'Not provided'}",
        f"Campaign field rep: {campaign_field_rep.get('name') or 'Not provided'}",
        f"Assigned field rep: {assigned_field_rep.get('name') or 'Not provided'}",
        f"Current RFA status: {instruction.get('current_status') or 'Not provided'}",
        f"Uploaded at: {instruction.get('uploaded_at') or 'Not provided'}",
    ]
    return "\n".join(lines)


def build_special_instruction_review_values(
    *,
    ticket,
    source_reference,
    payload,
    doctor,
    clinic,
    campaign,
    campaign_field_rep,
    assigned_field_rep,
    instruction,
):
    return {
        "ticket": ticket,
        "source_reference": source_reference,
        "doctor_id": doctor.get("id") or "",
        "doctor_name": doctor.get("name") or "",
        "doctor_email": doctor.get("email") or "",
        "clinic_name": clinic.get("name") or "",
        "clinic_phone": clinic.get("phone") or "",
        "campaign_uuid": campaign.get("campaign_id") or "",
        "campaign_name": campaign.get("campaign_name") or "",
        "brand_name": campaign.get("brand_name") or "",
        "campaign_field_rep_id": campaign_field_rep.get("id") or "",
        "campaign_field_rep_internal_id": safe_int(campaign_field_rep.get("internal_id")),
        "campaign_field_rep_name": campaign_field_rep.get("name") or "",
        "assigned_field_rep_id": assigned_field_rep.get("id") or "",
        "assigned_field_rep_internal_id": safe_int(assigned_field_rep.get("internal_id")),
        "assigned_field_rep_name": assigned_field_rep.get("name") or "",
        "rfa_current_status": instruction.get("current_status") or "",
        "rfa_status_code": instruction.get("status_code") or "",
        "uploaded_at": parse_payload_datetime(instruction.get("uploaded_at")),
        "download_url": clean_payload_url(instruction.get("download_url")),
        "approve_url": clean_payload_url(instruction.get("approve_url")),
        "payload": payload or {},
        "last_fetched_at": timezone.now(),
    }


def update_existing_special_instruction_ticket(ticket, title, description, campaign, doctor, clinic):
    changed_fields = []
    updates = {
        "title": title,
        "description": description,
        "campaign": campaign,
        "requester_name": doctor.get("name") or doctor.get("id") or ticket.requester_name,
        "requester_email": doctor.get("email") or ticket.requester_email,
        "requester_number": clinic.get("phone") or ticket.requester_number,
        "requester_company": clinic.get("name") or ticket.requester_company,
    }
    for field, value in updates.items():
        if getattr(ticket, field) != value:
            setattr(ticket, field, value)
            changed_fields.append(field)
    if changed_fields:
        ticket.save(update_fields=[*changed_fields, "updated_at"])


def resolve_project_manager_user(actor=None):
    if actor and getattr(actor, "is_authenticated", False):
        return actor
    user = User.objects.filter(email__iexact=settings.PROJECT_MANAGER_EMAIL).first()
    if user:
        return user
    user = User.objects.filter(role=User.Role.PROJECT_MANAGER, is_active=True).order_by("email").first()
    if user:
        return user
    user = User.objects.filter(is_superuser=True, is_active=True).order_by("email").first()
    if user:
        return user
    raise SpecialInstructionAPIError("No project manager user is configured for Special Instruction ticket creation.")


def resolve_special_instruction_review_department():
    code = settings.SPECIAL_INSTRUCTION_REVIEW_DEPARTMENT_CODE
    department = None
    if code:
        department = Department.objects.filter(code__iexact=code, is_active=True).select_related("default_recipient").first()
    if not department:
        department = Department.objects.filter(default_recipient__isnull=False, is_active=True).select_related("default_recipient").first()
    if not department:
        raise SpecialInstructionAPIError("No active department is configured for Special Instruction review tickets.")
    return department


def resolve_local_campaign(campaign_payload):
    campaign_id = str((campaign_payload or {}).get("campaign_id") or "").strip()
    campaign_name = str((campaign_payload or {}).get("campaign_name") or "").strip()
    brand_name = str((campaign_payload or {}).get("brand_name") or "").strip()
    if campaign_id:
        campaign = Campaign.objects.filter(slug__iexact=campaign_id).first()
        if campaign:
            return campaign
    if campaign_name:
        campaign = Campaign.objects.filter(name__iexact=campaign_name).first()
        if campaign:
            return campaign
    if brand_name:
        return Campaign.objects.filter(brand_name__iexact=brand_name).order_by("name").first()
    return None


def parse_payload_datetime(value):
    parsed = parse_datetime(str(value or "").strip()) if value else None
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone=dt_timezone.utc)
    return parsed


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_special_instruction_review(ticket):
    try:
        return ticket.special_instruction_review
    except SpecialInstructionReview.DoesNotExist:
        return None


def _download_path(doctor_id):
    return f"/internal/special-instructions/{quote(doctor_id)}/download/"


def _approve_path(doctor_id):
    return f"/internal/special-instructions/{quote(doctor_id)}/approve/"


def _extract_status_label(payload):
    ticket = (payload or {}).get("ticket") or {}
    instruction = ticket.get("special_instruction") or {}
    return instruction.get("current_status") or (payload or {}).get("current_status") or ""


def _extract_status_code(payload):
    ticket = (payload or {}).get("ticket") or {}
    instruction = ticket.get("special_instruction") or {}
    return instruction.get("status_code") or (payload or {}).get("status_code") or ""


def _json_error_message(payload, method, url, status_code):
    return (payload or {}).get("error") or (payload or {}).get("message") or f"{method} {url} failed with status {status_code}."


def _response_error_message(response, method, url):
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return _json_error_message(payload, method, url, response.status_code)
