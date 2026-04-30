from collections import OrderedDict
import logging

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.text import Truncator

from apps.ticketing.models import Department, Ticket
from apps.ticketing.services import create_ticket, resolve_ticket_classification

from .models import SupportCategory, SupportItem, SupportPage, SupportRequest, SupportSuperCategory, SupportWidgetEvent


ROLE_VISIBILITY_FIELD = {
    "doctor": "is_visible_to_doctors",
    "clinic_staff": "is_visible_to_clinic_staff",
    "brand_manager": "is_visible_to_brand_managers",
    "publisher": "is_visible_to_publishers",
    "field_rep": "is_visible_to_field_reps",
    "patient": "is_visible_to_patients",
    "student": "is_visible_to_students",
    "expert": "is_visible_to_experts",
}
GENERAL_SUPPORT_FLOW = "General support"
SOURCE_SYSTEM_TO_TICKET_SOURCE = {
    "In-clinic": Ticket.SourceSystem.IN_CLINIC,
    "Red Flag Alert": Ticket.SourceSystem.RED_FLAG_ALERT,
    "Patient Education": Ticket.SourceSystem.PATIENT_EDUCATION,
}
logger = logging.getLogger(__name__)


def get_visible_support_items(user_type):
    field_name = ROLE_VISIBILITY_FIELD.get(user_type)
    if not field_name:
        return SupportItem.objects.none()
    return (
        SupportItem.objects.filter(
            is_active=True,
            category__is_active=True,
            category__super_category__is_active=True,
            **{field_name: True},
        )
        .select_related("category__super_category", "ticket_department")
        .order_by("display_order", "name")
    )


def get_visible_faq_items(user_type):
    return get_visible_support_items(user_type).filter(knowledge_type=SupportItem.KnowledgeType.FAQ)


def get_faq_super_category_overview(user_type):
    overview = OrderedDict()
    for item in get_visible_faq_items(user_type):
        super_category = item.category.super_category
        category = item.category
        if super_category.pk not in overview:
            overview[super_category.pk] = {
                "super_category": super_category,
                "categories": OrderedDict(),
                "faq_count": 0,
            }
        category_bucket = overview[super_category.pk]["categories"]
        if category.pk not in category_bucket:
            category_bucket[category.pk] = {
                "category": category,
                "faq_items": [],
            }
        category_bucket[category.pk]["faq_items"].append(item)
        overview[super_category.pk]["faq_count"] += 1

    results = []
    for block in overview.values():
        categories = list(block["categories"].values())
        results.append(
            {
                "super_category": block["super_category"],
                "faq_count": block["faq_count"],
                "category_count": len(categories),
                "categories": categories,
            }
        )
    return results


def get_faq_page_overview(user_type):
    overview = OrderedDict()
    for item in get_visible_faq_items(user_type):
        page = item.page
        if not page:
            continue
        if page.pk not in overview:
            overview[page.pk] = {
                "page": page,
                "faq_count": 0,
                "sections": OrderedDict(),
            }
        section_bucket = overview[page.pk]["sections"]
        super_category = item.category.super_category
        if super_category.pk not in section_bucket:
            section_bucket[super_category.pk] = {
                "super_category": super_category,
                "faq_items": [],
                "categories": OrderedDict(),
            }
        section_bucket[super_category.pk]["faq_items"].append(item)
        section_bucket[super_category.pk]["categories"][item.category_id] = item.category
        overview[page.pk]["faq_count"] += 1

    results = []
    for block in overview.values():
        sections = []
        for section in block["sections"].values():
            sections.append(
                {
                    "super_category": section["super_category"],
                    "faq_items": section["faq_items"],
                    "faq_count": len(section["faq_items"]),
                    "category_names": [category.name for category in section["categories"].values()],
                }
            )
        results.append(
            {
                "page": block["page"],
                "faq_count": block["faq_count"],
                "section_count": len(sections),
                "sections": sections,
            }
        )
    return results


def get_faq_page(user_type, page_slug):
    for block in get_faq_page_overview(user_type):
        if block["page"].slug == page_slug:
            return block
    return None


def get_faq_super_category(user_type, super_slug):
    for block in get_faq_super_category_overview(user_type):
        if block["super_category"].slug == super_slug:
            return block
    return None


def get_faq_items_for_combination(user_type, super_slug, category_slug):
    return list(
        get_visible_faq_items(user_type)
        .filter(category__slug=category_slug, category__super_category__slug=super_slug)
        .order_by("display_order", "name")
    )


def get_faq_combination(user_type, super_slug, category_slug):
    faq_items = get_faq_items_for_combination(user_type, super_slug, category_slug)
    if not faq_items:
        return None
    category = faq_items[0].category
    super_category = category.super_category
    source_systems = [item.source_system for item in faq_items if item.source_system]
    source_flows = [item.source_flow for item in faq_items if item.source_flow]
    return {
        "super_category": super_category,
        "category": category,
        "faq_items": faq_items,
        "faq_count": len(faq_items),
        "source_system": source_systems[0] if len(set(source_systems)) == 1 else "",
        "source_flow": source_flows[0] if len(set(source_flows)) == 1 else "",
    }


def get_available_systems(user_type):
    systems = []
    seen = set()
    for system_name in get_visible_support_items(user_type).values_list("source_system", flat=True):
        if system_name and system_name not in seen:
            systems.append(system_name)
            seen.add(system_name)
    return systems


def _flow_query(flow_name):
    if flow_name == GENERAL_SUPPORT_FLOW:
        return Q(source_flow="")
    return Q(source_flow=flow_name)


def get_available_flows(user_type, system_name):
    flows = []
    seen = set()
    queryset = get_visible_support_items(user_type).filter(source_system=system_name)
    for flow_name in queryset.values_list("source_flow", flat=True):
        label = flow_name or GENERAL_SUPPORT_FLOW
        if label not in seen:
            flows.append(label)
            seen.add(label)
    return flows


def get_available_categories(user_type, system_name, flow_name):
    queryset = get_visible_support_items(user_type).filter(source_system=system_name).filter(_flow_query(flow_name))
    categories = []
    seen = set()
    for item in queryset:
        if item.category_id not in seen:
            categories.append(item.category)
            seen.add(item.category_id)
    return categories


def get_issue_sequences(user_type, system_name, flow_name, category_id):
    queryset = (
        get_visible_support_items(user_type)
        .filter(source_system=system_name, category_id=category_id)
        .filter(_flow_query(flow_name))
    )
    faqs = [item for item in queryset if item.knowledge_type == SupportItem.KnowledgeType.FAQ]
    ticket_cases = [item for item in queryset if item.knowledge_type == SupportItem.KnowledgeType.TICKET_CASE]
    return faqs, ticket_cases


def _ticket_source_system(item):
    if not item:
        return Ticket.SourceSystem.CUSTOMER_SUPPORT
    return SOURCE_SYSTEM_TO_TICKET_SOURCE.get(item.source_system, Ticket.SourceSystem.CUSTOMER_SUPPORT)


def _resolve_department(item):
    if item and item.ticket_department_id:
        return item.ticket_department
    return Department.objects.filter(default_recipient__isnull=False, is_active=True).first()


def _fallback_requester_identity(user_type, request_user):
    if request_user and request_user.is_authenticated:
        return {
            "name": request_user.full_name or settings.PROJECT_MANAGER_EMAIL,
            "email": request_user.email,
            "number": request_user.phone_number or "",
            "company": request_user.company or "",
        }
    return {
        "name": f"{user_type.replace('_', ' ').title()} support user",
        "email": f"{user_type}.widget@support-widget.local",
        "number": "",
        "company": "",
    }


def get_pm_queue_estimated_response_time():
    return settings.PM_QUEUE_ESTIMATED_RESPONSE_TIME


def build_pm_queue_success_message(support_request):
    return (
        f"Your ticket ID is {support_request.queue_ticket_number}. "
        f"Estimated response time: {get_pm_queue_estimated_response_time()}."
    )


def _pm_queue_email_context(support_request):
    return {
        "support_request": support_request,
        "ticket_id": support_request.queue_ticket_number,
        "estimated_response_time": get_pm_queue_estimated_response_time(),
        "device_type": support_request.get_device_type_display() if support_request.device_type else "",
        "device": support_request.get_device_display() if support_request.device else "",
    }


def _send_email_via_sendgrid(*, to_email, to_name, subject, text_body, html_body):
    response = requests.post(
        settings.SENDGRID_API_URL,
        headers={
            "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "personalizations": [
                {
                    "to": [{"email": to_email, "name": to_name or to_email}],
                    "subject": subject,
                }
            ],
            "from": {
                "email": settings.SENDGRID_FROM_EMAIL,
                "name": settings.SENDGRID_FROM_NAME,
            },
            "content": [
                {"type": "text/plain", "value": text_body},
                {"type": "text/html", "value": html_body},
            ],
        },
        timeout=10,
    )
    response.raise_for_status()


def _send_email_via_django(*, to_email, subject, text_body, html_body):
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)


def send_pm_queue_confirmation_email(support_request):
    if not support_request.requester_email:
        return

    context = _pm_queue_email_context(support_request)
    subject = f"Support ticket {support_request.queue_ticket_number} received"
    text_body = render_to_string("support_center/emails/pm_queue_confirmation.txt", context)
    html_body = render_to_string("support_center/emails/pm_queue_confirmation.html", context)

    try:
        if settings.SENDGRID_API_KEY:
            _send_email_via_sendgrid(
                to_email=support_request.requester_email,
                to_name=support_request.requester_name,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )
        else:
            _send_email_via_django(
                to_email=support_request.requester_email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )
    except Exception:
        logger.exception(
            "PM queue confirmation email failed for support request %s",
            support_request.queue_ticket_number,
        )


def create_support_widget_event(
    *,
    event_type,
    user_type,
    page=None,
    super_category=None,
    category=None,
    support_request=None,
    system_name="",
    flow_name="",
):
    return SupportWidgetEvent.objects.create(
        user_type=user_type,
        support_page=page,
        support_super_category=super_category,
        support_category=category,
        support_request=support_request,
        source_system=system_name or "",
        source_flow="" if flow_name == GENERAL_SUPPORT_FLOW else (flow_name or ""),
        event_type=event_type,
    )


def create_other_support_request(*, user_type, page, super_category, category, system_name, flow_name, form, request_user, origin_channel):
    support_request = form.save(commit=False)
    requester = _fallback_requester_identity(user_type, request_user)
    support_request.user_type = user_type
    support_request.item = None
    support_request.support_page = page
    support_request.support_super_category = super_category
    support_request.support_category = category
    support_request.source_system = system_name or ""
    support_request.source_flow = "" if flow_name == GENERAL_SUPPORT_FLOW else (flow_name or "")
    support_request.origin_channel = origin_channel
    support_request.requester_name = (support_request.requester_name or requester["name"]).strip()
    support_request.requester_email = (support_request.requester_email or requester["email"]).strip()
    support_request.requester_number = (support_request.requester_number or requester["number"]).strip()
    support_request.requester_company = requester["company"]
    support_request.subject = f"Other issue - {(page.name if page else category.name)}"
    support_request.status = SupportRequest.Status.PENDING_PM_REVIEW
    support_request.save()
    send_pm_queue_confirmation_email(support_request)
    return support_request


def resolve_support_request_context(*, selected_faq=None, selected_system="", selected_flow=""):
    system_name = selected_system or ""
    flow_name = selected_flow or ""
    if not system_name and selected_faq:
        system_name = selected_faq.source_system or system_name
    if not flow_name and selected_faq and (
        not system_name or system_name == (selected_faq.source_system or "")
    ):
        flow_name = selected_faq.source_flow or flow_name
    return {
        "system_name": system_name,
        "flow_name": flow_name or GENERAL_SUPPORT_FLOW,
    }


def build_support_request_ticket_initial(support_request):
    description_lines = [
        support_request.free_text.strip(),
        "",
        "Support request context",
        f"PM queue ticket ID: {support_request.queue_ticket_number or 'Not available'}",
        f"PM queue priority: {support_request.priority_label}",
        f"System: {support_request.source_system or 'Not provided'}",
        f"Flow: {support_request.source_flow or GENERAL_SUPPORT_FLOW}",
        f"Page: {support_request.page_label or 'Not specified'}",
        f"Section: {support_request.section_label or 'Not specified'}",
        f"Screen / Section: {support_request.screen_label or 'Not specified'}",
        f"User type: {support_request.user_type.replace('_', ' ').title()}",
        f"Requester name: {support_request.requester_name or 'Not provided'}",
        f"Requester email: {support_request.requester_email or 'Not provided'}",
        f"Requester phone: {support_request.requester_number or 'Not provided'}",
        f"Requester company: {support_request.requester_company or 'Not provided'}",
        f"Device type: {support_request.get_device_type_display() if support_request.device_type else 'Not provided'}",
        f"Device: {support_request.get_device_display() if support_request.device else 'Not provided'}",
    ]
    if support_request.uploaded_file:
        description_lines.append(f"Uploaded file: {support_request.uploaded_file.name.split('/')[-1]}")

    classification = resolve_ticket_classification(
        title=support_request.subject,
        source_system=SOURCE_SYSTEM_TO_TICKET_SOURCE.get(
            support_request.source_system,
            Ticket.SourceSystem.CUSTOMER_SUPPORT,
        ),
    )
    return {
        "title": Truncator(support_request.free_text or support_request.subject).chars(80),
        "description": "\n".join(line for line in description_lines if line is not None),
        "ticket_category": classification["ticket_category"],
        "ticket_type_definition": classification["ticket_type_definition"],
        "priority": Ticket.Priority.CRITICAL if support_request.is_escalated else classification["priority"],
        "campaign": support_request.campaign,
        "user_type": support_request.user_type,
        "source_system": SOURCE_SYSTEM_TO_TICKET_SOURCE.get(
            support_request.source_system,
            Ticket.SourceSystem.CUSTOMER_SUPPORT,
        ),
        "requester_name": support_request.requester_name,
        "requester_email": support_request.requester_email,
        "requester_number": support_request.requester_number,
        "requester_company": support_request.requester_company,
    }


def submit_support_request(*, item, user_type, form, request_user):
    support_request = form.save(commit=False)
    support_request.user_type = user_type
    support_request.item = item
    support_request.support_page = item.page if item else None
    support_request.support_super_category = item.category.super_category if item else None
    support_request.support_category = item.category if item else None
    if request_user and request_user.is_authenticated and not support_request.requester_number:
        support_request.requester_number = request_user.phone_number or ""
    department = _resolve_department(item)

    if item and item.ticket_required is False:
        support_request.status = support_request.Status.SOLUTION_PROVIDED
        support_request.save()
        return support_request, None, "This issue is documented as a non-ticket case. No ticket was raised."

    if not department or not department.default_recipient:
        support_request.status = support_request.Status.SOLUTION_PROVIDED
        support_request.save()
        return support_request, None, "No support department recipient has been configured yet."

    support_request.status = support_request.Status.TICKET_CREATED
    support_request.save()
    ticket = create_ticket(
        title=item.name if item else support_request.subject,
        description=support_request.free_text or (item.summary if item else support_request.subject) or support_request.subject,
        ticket_type=item.default_ticket_type if item else "General support request",
        user_type=user_type,
        source_system=_ticket_source_system(item),
        priority=Ticket.Priority.MEDIUM,
        department=department,
        campaign=support_request.campaign,
        created_by=request_user if request_user.is_authenticated else None,
        submitted_by=request_user if request_user.is_authenticated else None,
        direct_recipient=department.default_recipient,
        current_assignee=department.default_recipient,
        requester_name=support_request.requester_name,
        requester_email=support_request.requester_email,
        requester_company=support_request.requester_company,
        is_escalated=support_request.is_escalated,
        support_request=support_request,
        support_item=item,
    )
    return support_request, ticket, None
