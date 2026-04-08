from collections import OrderedDict

from django.conf import settings
from django.db.models import Q
from django.utils.text import Truncator

from apps.ticketing.models import Department, Ticket
from apps.ticketing.services import create_ticket, resolve_ticket_classification

from .models import SupportCategory, SupportItem, SupportRequest, SupportSuperCategory


ROLE_VISIBILITY_FIELD = {
    "doctor": "is_visible_to_doctors",
    "clinic_staff": "is_visible_to_clinic_staff",
    "brand_manager": "is_visible_to_brand_managers",
    "field_rep": "is_visible_to_field_reps",
    "patient": "is_visible_to_patients",
}
GENERAL_SUPPORT_FLOW = "General support"
SOURCE_SYSTEM_TO_TICKET_SOURCE = {
    "In-clinic": Ticket.SourceSystem.IN_CLINIC,
    "Red Flag Alert": Ticket.SourceSystem.RED_FLAG_ALERT,
    "Patient Education": Ticket.SourceSystem.PATIENT_EDUCATION,
}


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
    return {
        "super_category": super_category,
        "category": category,
        "faq_items": faq_items,
        "faq_count": len(faq_items),
        "source_system": faq_items[0].source_system,
        "source_flow": faq_items[0].source_flow,
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
            "company": request_user.company or "",
        }
    return {
        "name": f"{user_type.replace('_', ' ').title()} support user",
        "email": f"{user_type}.widget@support-widget.local",
        "company": "",
    }


def create_other_support_request(*, user_type, category, system_name, flow_name, form, request_user):
    support_request = form.save(commit=False)
    requester = _fallback_requester_identity(user_type, request_user)
    support_request.user_type = user_type
    support_request.item = None
    support_request.support_category = category
    support_request.source_system = system_name or ""
    support_request.source_flow = "" if flow_name == GENERAL_SUPPORT_FLOW else (flow_name or "")
    support_request.requester_name = requester["name"]
    support_request.requester_email = requester["email"]
    support_request.requester_company = requester["company"]
    support_request.subject = f"Other issue - {category.name}"
    support_request.status = SupportRequest.Status.PENDING_PM_REVIEW
    support_request.save()
    return support_request


def build_support_request_ticket_initial(support_request):
    description_lines = [
        support_request.free_text.strip(),
        "",
        "Support request context",
        f"System: {support_request.source_system or 'Customer support'}",
        f"Flow: {support_request.source_flow or GENERAL_SUPPORT_FLOW}",
        f"Screen / Section: {support_request.screen_label or 'Not specified'}",
        f"User type: {support_request.user_type.replace('_', ' ').title()}",
        f"Requester name: {support_request.requester_name or 'Not provided'}",
        f"Requester email: {support_request.requester_email or 'Not provided'}",
        f"Requester company: {support_request.requester_company or 'Not provided'}",
    ]
    if support_request.uploaded_file:
        description_lines.append(f"Uploaded file: {support_request.uploaded_file.name}")

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
        "priority": classification["priority"],
        "campaign": support_request.campaign,
        "user_type": support_request.user_type,
        "source_system": SOURCE_SYSTEM_TO_TICKET_SOURCE.get(
            support_request.source_system,
            Ticket.SourceSystem.CUSTOMER_SUPPORT,
        ),
        "requester_name": support_request.requester_name,
        "requester_email": support_request.requester_email,
        "requester_company": support_request.requester_company,
    }


def submit_support_request(*, item, user_type, form, request_user):
    support_request = form.save(commit=False)
    support_request.user_type = user_type
    support_request.item = item
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
        support_request=support_request,
        support_item=item,
    )
    return support_request, ticket, None
