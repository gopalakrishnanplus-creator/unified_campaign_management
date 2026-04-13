from collections import Counter, defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.text import slugify

from .models import Ticket, TicketCategory, TicketRoutingEvent, TicketTypeDefinition


TICKET_TAXONOMY = [
    {
        "name": "Bug",
        "description": "Unexpected defects, errors, failures, and regressions.",
        "types": {
            "Functional": "Business logic or workflow is not behaving as expected.",
            "UI": "Layout, rendering, interaction, or visual behavior issue.",
            "Performance": "Slow response times, lag, or degraded performance.",
            "Error": "Exceptions, crashes, or explicit error states.",
        },
    },
    {
        "name": "Feature Request",
        "description": "Requested product capabilities and improvement ideas.",
        "types": {
            "New Feature": "A new capability that does not exist yet.",
            "Enhancement": "An improvement to an existing capability.",
        },
    },
    {
        "name": "Data Issue",
        "description": "Problems with expected data being delayed, missing, or wrong.",
        "types": {
            "Missing": "Expected records or outputs are absent.",
            "Incorrect": "Data is present but wrong or inconsistent.",
            "Delay": "Data is arriving late or processing is delayed.",
        },
    },
    {
        "name": "Access",
        "description": "Login and access-control issues.",
        "types": {
            "Login": "Unable to authenticate or sign in.",
            "Permission": "Authenticated user lacks the required access.",
        },
    },
    {
        "name": "Integration",
        "description": "Failures or sync issues across connected systems.",
        "types": {
            "Failure": "A connected integration is failing outright.",
            "Sync": "Data or state is not syncing correctly.",
        },
    },
    {
        "name": "Billing",
        "description": "Billing, payment, invoice, or subscription concerns.",
        "types": {
            "Invoice": "Invoice generation, access, or mismatch issue.",
            "Payment": "Payment processing or settlement issue.",
            "Subscription": "Subscription lifecycle or entitlement issue.",
        },
    },
    {
        "name": "Support",
        "description": "General guidance requests and user questions.",
        "types": {
            "How-to": "User needs product guidance or training help.",
            "Query": "General support question or clarification.",
        },
    },
    {
        "name": "Content",
        "description": "Issues with content accuracy, freshness, or asset updates.",
        "types": {
            "Incorrect": "Displayed content is wrong or outdated.",
            "Update": "Requested refresh or update to content/assets.",
        },
    },
    {
        "name": "Incident",
        "description": "High-severity incidents affecting availability or large groups of users.",
        "types": {
            "System Down": "Service outage or effectively unavailable system.",
            "High Impact": "Broad or critical production impact requiring urgent attention.",
        },
    },
]

CLASSIFICATION_RULES = [
    {
        "keywords": ("login", "sign-in", "signin", "authentication", "credential", "otp", "password"),
        "category": "Access",
        "ticket_type": "Login",
        "description": "Unable to authenticate or sign in.",
    },
    {
        "keywords": ("permission", "access denied", "not authorized", "forbidden", "role access"),
        "category": "Access",
        "ticket_type": "Permission",
        "description": "Authenticated user lacks required access.",
    },
    {
        "keywords": ("missing report", "delayed report", "delay", "pending data", "report delayed"),
        "category": "Data Issue",
        "ticket_type": "Delay",
        "description": "Expected reporting or system data is delayed.",
    },
    {
        "keywords": ("missing", "not showing", "not visible", "not available", "not added"),
        "category": "Data Issue",
        "ticket_type": "Missing",
        "description": "Expected data or records are missing.",
    },
    {
        "keywords": ("incorrect", "wrong", "mismatch", "inaccurate", "duplicate"),
        "category": "Data Issue",
        "ticket_type": "Incorrect",
        "description": "Data is present but incorrect.",
    },
    {
        "keywords": ("invoice",),
        "category": "Billing",
        "ticket_type": "Invoice",
        "description": "Invoice-related issue.",
    },
    {
        "keywords": ("payment", "paid", "transaction"),
        "category": "Billing",
        "ticket_type": "Payment",
        "description": "Payment-related issue.",
    },
    {
        "keywords": ("subscription", "renewal", "plan"),
        "category": "Billing",
        "ticket_type": "Subscription",
        "description": "Subscription-related issue.",
    },
    {
        "keywords": ("sync", "synchronization", "not synced"),
        "category": "Integration",
        "ticket_type": "Sync",
        "description": "Connected systems are not syncing correctly.",
    },
    {
        "keywords": ("api", "integration", "webhook", "connector", "failure"),
        "category": "Integration",
        "ticket_type": "Failure",
        "description": "Connected integration is failing.",
    },
    {
        "keywords": ("system down", "outage", "site down", "service unavailable", "503"),
        "category": "Incident",
        "ticket_type": "System Down",
        "description": "Service outage or unavailable system.",
    },
    {
        "keywords": ("critical", "urgent", "major impact", "high impact", "sev1"),
        "category": "Incident",
        "ticket_type": "High Impact",
        "description": "Broad or critical production impact.",
    },
    {
        "keywords": ("slow", "latency", "performance", "lag", "timeout"),
        "category": "Bug",
        "ticket_type": "Performance",
        "description": "Performance issue or degraded responsiveness.",
    },
    {
        "keywords": ("ui", "layout", "button", "screen", "page design", "alignment"),
        "category": "Bug",
        "ticket_type": "UI",
        "description": "Visual or interaction issue.",
    },
    {
        "keywords": ("error", "exception", "crash", "stack trace", "500"),
        "category": "Bug",
        "ticket_type": "Error",
        "description": "Explicit error, exception, or crash.",
    },
    {
        "keywords": ("not working", "broken", "issue", "bug", "fail to open", "cannot open"),
        "category": "Bug",
        "ticket_type": "Functional",
        "description": "Functional defect or regression.",
    },
    {
        "keywords": ("feature request", "new feature", "build", "add support for"),
        "category": "Feature Request",
        "ticket_type": "New Feature",
        "description": "Request for a brand-new capability.",
    },
    {
        "keywords": ("enhancement", "improve", "improvement", "better way"),
        "category": "Feature Request",
        "ticket_type": "Enhancement",
        "description": "Request to improve an existing capability.",
    },
    {
        "keywords": ("how to", "how-to", "steps", "guide", "help me"),
        "category": "Support",
        "ticket_type": "How-to",
        "description": "User needs guidance or training help.",
    },
    {
        "keywords": ("query", "question", "clarify", "clarification"),
        "category": "Support",
        "ticket_type": "Query",
        "description": "General support question.",
    },
    {
        "keywords": ("content", "collateral", "pdf", "video", "banner", "creative"),
        "category": "Content",
        "ticket_type": "Update",
        "description": "Content asset needs refresh or update.",
    },
    {
        "keywords": ("wrong content", "incorrect content", "outdated", "stale content"),
        "category": "Content",
        "ticket_type": "Incorrect",
        "description": "Displayed content is incorrect or outdated.",
    },
]

SUPPORT_ITEM_CATEGORY_HINTS = [
    ("collateral", ("Content", "Update")),
    ("content", ("Content", "Update")),
    ("patient education", ("Content", "Update")),
    ("report", ("Data Issue", "Delay")),
    ("analytics", ("Data Issue", "Incorrect")),
    ("campaign", ("Data Issue", "Missing")),
    ("onboarding", ("Data Issue", "Missing")),
    ("red flag", ("Bug", "Functional")),
    ("follow-up", ("Bug", "Functional")),
    ("login", ("Access", "Login")),
    ("authentication", ("Access", "Login")),
    ("access", ("Access", "Login")),
]

SOURCE_SYSTEM_FALLBACKS = {
    Ticket.SourceSystem.IN_CLINIC: ("Content", "Update"),
    Ticket.SourceSystem.RED_FLAG_ALERT: ("Bug", "Functional"),
    Ticket.SourceSystem.PATIENT_EDUCATION: ("Content", "Update"),
    Ticket.SourceSystem.CUSTOMER_SUPPORT: ("Support", "Query"),
    Ticket.SourceSystem.PROJECT_MANAGER: ("Support", "Query"),
    Ticket.SourceSystem.MANUAL: ("Support", "Query"),
}


def _normalize_text(value):
    return str(value or "").strip().lower()


def seed_default_ticket_taxonomy():
    seeded_categories = {}
    for order, category_config in enumerate(TICKET_TAXONOMY, start=1):
        category = get_or_create_ticket_category(
            category_config["name"],
            description=category_config["description"],
            display_order=order,
        )
        seeded_categories[category.name] = category
        for ticket_type_name, description in category_config["types"].items():
            get_or_create_ticket_type_definition(
                category=category,
                name=ticket_type_name,
                description=description,
            )
    return seeded_categories


def _taxonomy_map():
    return {item["name"]: set(item["types"].keys()) for item in TICKET_TAXONOMY}


def _default_type_for_category(category_name):
    for item in TICKET_TAXONOMY:
        if item["name"] == category_name:
            return next(iter(item["types"].keys()))
    return "Query"


def get_or_create_ticket_category(name, description="", display_order=0):
    category, created = TicketCategory.objects.get_or_create(
        slug=slugify(name),
        defaults={"name": name, "description": description, "display_order": display_order},
    )
    if not created:
        changed = False
        if category.name != name:
            category.name = name
            changed = True
        if description and category.description != description:
            category.description = description
            changed = True
        if display_order and category.display_order != display_order:
            category.display_order = display_order
            changed = True
        if changed:
            category.save(update_fields=["name", "description", "display_order"])
    return category


def get_or_create_ticket_type_definition(
    *,
    category,
    name,
    description="",
    department=None,
    source_system=Ticket.SourceSystem.MANUAL,
    default_priority=Ticket.Priority.MEDIUM,
):
    ticket_type, created = TicketTypeDefinition.objects.get_or_create(
        category=category,
        slug=slugify(name),
        defaults={
            "name": name,
            "description": description,
            "default_department": department,
            "default_source_system": source_system,
            "default_priority": default_priority,
        },
    )
    if not created:
        changed = False
        if ticket_type.name != name:
            ticket_type.name = name
            changed = True
        if description and ticket_type.description != description:
            ticket_type.description = description
            changed = True
        if not ticket_type.default_department_id and department:
            ticket_type.default_department = department
            changed = True
        if source_system and ticket_type.default_source_system != source_system:
            ticket_type.default_source_system = source_system
            changed = True
        if default_priority and ticket_type.default_priority != default_priority:
            ticket_type.default_priority = default_priority
            changed = True
        if changed:
            ticket_type.save(update_fields=["name", "description", "default_department", "default_source_system", "default_priority"])
    return ticket_type


def infer_ticket_taxonomy(*, title, source_system, support_item=None):
    if support_item:
        support_text = " ".join(
            [
                getattr(support_item, "name", ""),
                getattr(support_item, "summary", ""),
                getattr(getattr(support_item, "category", None), "name", ""),
                getattr(getattr(getattr(support_item, "category", None), "super_category", None), "name", ""),
            ]
        )
        normalized_support_text = _normalize_text(support_text)
        for keyword, result in SUPPORT_ITEM_CATEGORY_HINTS:
            if keyword in normalized_support_text:
                return result

    title_normalized = _normalize_text(title)
    for rule in CLASSIFICATION_RULES:
        if any(keyword in title_normalized for keyword in rule["keywords"]):
            return rule["category"], rule["ticket_type"]

    return SOURCE_SYSTEM_FALLBACKS.get(source_system, ("Support", "Query"))


def resolve_ticket_classification(
    *,
    title,
    ticket_type_name=None,
    ticket_category=None,
    ticket_type_definition=None,
    new_ticket_type_name=None,
    department=None,
    source_system=Ticket.SourceSystem.MANUAL,
    priority=Ticket.Priority.MEDIUM,
    support_item=None,
):
    seed_default_ticket_taxonomy()
    taxonomy_map = _taxonomy_map()

    if ticket_type_definition:
        if ticket_category and ticket_type_definition.category_id != ticket_category.id:
            raise ValueError("Selected ticket type does not belong to the chosen ticket category.")
        ticket_category = ticket_type_definition.category
        resolved_type_name = ticket_type_definition.name
        resolved_priority = priority or ticket_type_definition.default_priority
        return {
            "ticket_category": ticket_category,
            "ticket_type_definition": ticket_type_definition,
            "ticket_type_name": resolved_type_name,
            "priority": resolved_priority,
        }

    if ticket_category and ticket_category.name not in taxonomy_map:
        ticket_category = None

    if not ticket_category:
        inferred_category_name, inferred_type_name = infer_ticket_taxonomy(
            title=ticket_type_name or new_ticket_type_name or title,
            source_system=source_system,
            support_item=support_item,
        )
        ticket_category = TicketCategory.objects.filter(slug=slugify(inferred_category_name)).first()
        if not ticket_category:
            ticket_category = get_or_create_ticket_category(inferred_category_name)
    else:
        inferred_type_name = None

    resolved_type_name = (new_ticket_type_name or ticket_type_name or inferred_type_name or title).strip()
    if not new_ticket_type_name:
        valid_types = taxonomy_map.get(ticket_category.name, set())
        if valid_types and resolved_type_name not in valid_types:
            resolved_type_name = inferred_type_name or _default_type_for_category(ticket_category.name)

    ticket_type_definition = get_or_create_ticket_type_definition(
        category=ticket_category,
        name=resolved_type_name,
        description=f"Classified under {ticket_category.name}.",
        department=department,
        source_system=source_system,
        default_priority=priority,
    )
    return {
        "ticket_category": ticket_category,
        "ticket_type_definition": ticket_type_definition,
        "ticket_type_name": ticket_type_definition.name,
        "priority": priority or ticket_type_definition.default_priority,
    }


@transaction.atomic
def create_ticket(**kwargs):
    classification = resolve_ticket_classification(
        title=kwargs["title"],
        ticket_type_name=kwargs.get("ticket_type"),
        ticket_category=kwargs.pop("ticket_category", None),
        ticket_type_definition=kwargs.pop("ticket_type_definition", None),
        new_ticket_type_name=kwargs.pop("new_ticket_type_name", None),
        department=kwargs.get("department"),
        source_system=kwargs.get("source_system", Ticket.SourceSystem.MANUAL),
        priority=kwargs.get("priority", Ticket.Priority.MEDIUM),
        support_item=kwargs.pop("support_item", None),
    )
    kwargs["ticket_category"] = classification["ticket_category"]
    kwargs["ticket_type_definition"] = classification["ticket_type_definition"]
    kwargs["ticket_type"] = classification["ticket_type_name"]
    kwargs["priority"] = classification["priority"]
    ticket = Ticket.objects.create(**kwargs)
    from .external_ticketing import should_sync_external_ticket, sync_external_ticket

    if should_sync_external_ticket(ticket):
        transaction.on_commit(lambda ticket_id=ticket.pk: sync_external_ticket(ticket_id))
    return ticket


@transaction.atomic
def delegate_ticket(ticket, actor, assignee):
    previous_assignee = ticket.current_assignee
    ticket.current_assignee = assignee
    ticket.save(update_fields=["current_assignee", "updated_at"])
    TicketRoutingEvent.objects.create(
        ticket=ticket,
        action=TicketRoutingEvent.Action.DELEGATED,
        actor=actor,
        from_user=previous_assignee,
        to_user=assignee,
        description=f"Delegated by {actor.email}.",
    )
    return ticket


@transaction.atomic
def escalate_ticket(ticket, actor):
    update_fields = ["updated_at"]
    if not ticket.is_escalated:
        ticket.is_escalated = True
        update_fields.append("is_escalated")
    if ticket.priority != Ticket.Priority.CRITICAL:
        ticket.priority = Ticket.Priority.CRITICAL
        update_fields.append("priority")
    if len(update_fields) > 1:
        ticket.save(update_fields=update_fields)

    if ticket.support_request_id and not ticket.support_request.is_escalated:
        ticket.support_request.is_escalated = True
        ticket.support_request.save(update_fields=["is_escalated"])

    TicketRoutingEvent.objects.create(
        ticket=ticket,
        action=TicketRoutingEvent.Action.ESCALATED,
        actor=actor,
        from_user=ticket.current_assignee,
        to_user=ticket.current_assignee,
        description="Marked as High Priority and moved to the top of the PM queue.",
    )
    return ticket


@transaction.atomic
def return_ticket_to_sender(ticket, actor):
    if not ticket.created_by:
        return ticket
    previous_assignee = ticket.current_assignee
    ticket.current_assignee = ticket.created_by
    ticket.save(update_fields=["current_assignee", "updated_at"])
    TicketRoutingEvent.objects.create(
        ticket=ticket,
        action=TicketRoutingEvent.Action.RETURNED,
        actor=actor,
        from_user=previous_assignee,
        to_user=ticket.created_by,
        description="Ticket returned to sender.",
    )
    return ticket


@transaction.atomic
def change_ticket_status(ticket, actor, new_status):
    old_status = ticket.get_status_display()
    ticket.status = new_status
    ticket.save(update_fields=["status", "resolved_at", "updated_at"])
    TicketRoutingEvent.objects.create(
        ticket=ticket,
        action=TicketRoutingEvent.Action.STATUS_CHANGED,
        actor=actor,
        from_user=ticket.current_assignee,
        to_user=ticket.current_assignee,
        description=f"Status changed from {old_status} to {ticket.get_status_display()}.",
    )
    return ticket


def build_ticket_distribution_data(queryset, period_days=30):
    since = timezone.now() - timedelta(days=period_days)
    tickets = queryset.filter(created_at__gte=since).select_related("ticket_category")
    if not tickets.exists():
        return {
            "labels": [],
            "totals": [],
            "by_category": [],
            "table_rows": [],
            "category_options": [],
        }

    totals_by_day = Counter()
    categories_by_day = defaultdict(Counter)
    label_dates = {}
    for ticket in tickets:
        local_dt = ticket.created_at.astimezone(timezone.get_current_timezone())
        label = local_dt.strftime("%d %b")
        label_dates[label] = local_dt.date()
        totals_by_day[label] += 1
        category_name = ticket.ticket_category.name if ticket.ticket_category else "Uncategorized"
        categories_by_day[category_name][label] += 1

    labels = [label for label, _date in sorted(label_dates.items(), key=lambda item: item[1])]
    by_category = []
    for category_name, counts in sorted(categories_by_day.items()):
        by_category.append({"label": category_name, "data": [counts.get(label, 0) for label in labels]})

    table_rows = []
    for label in labels:
        row = {"label": label, "total": totals_by_day.get(label, 0)}
        for category_entry in by_category:
            row[category_entry["label"]] = category_entry["data"][labels.index(label)]
        table_rows.append(row)

    return {
        "labels": labels,
        "totals": [totals_by_day.get(label, 0) for label in labels],
        "by_category": by_category,
        "table_rows": table_rows,
        "category_options": [entry["label"] for entry in by_category],
    }


def build_ticket_priority_summary(queryset):
    counts = queryset.values("priority").annotate(total=Count("id"))
    summary = {row["priority"]: row["total"] for row in counts}
    return {
        "low": summary.get(Ticket.Priority.LOW, 0),
        "medium": summary.get(Ticket.Priority.MEDIUM, 0),
        "high": summary.get(Ticket.Priority.HIGH, 0),
        "critical": summary.get(Ticket.Priority.CRITICAL, 0),
    }
