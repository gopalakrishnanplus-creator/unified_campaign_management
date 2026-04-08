from collections import defaultdict
from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings
from django.db.models import Case, Count, IntegerField, When
from django.test import Client
from django.urls import reverse

from apps.campaigns.models import Campaign
from apps.reporting.services import build_live_performance_sections
from apps.support_center.models import SupportRequest
from apps.ticketing.models import Ticket
from apps.ticketing.services import build_ticket_distribution_data


STATUS_COLOR_MAP = {
    200: "success",
    201: "success",
    204: "success",
    301: "info",
    302: "info",
    400: "warning",
    401: "warning",
    403: "warning",
    404: "warning",
    500: "danger",
    502: "danger",
    503: "danger",
    504: "danger",
}

CHART_PALETTE = ["#0f766e", "#1d4ed8", "#f59e0b", "#7c3aed", "#dc2626", "#0891b2", "#475569"]
STATUS_BADGE_CLASS = {
    Ticket.Status.NOT_STARTED: "status-not-started",
    Ticket.Status.IN_PROCESS: "status-in-process",
    Ticket.Status.ON_HOLD: "status-on-hold",
    Ticket.Status.CANNOT_COMPLETE: "status-cannot-complete",
    Ticket.Status.COMPLETED: "status-completed",
}
PRIORITY_BADGE_CLASS = {
    Ticket.Priority.LOW: "priority-low",
    Ticket.Priority.MEDIUM: "priority-medium",
    Ticket.Priority.HIGH: "priority-high",
    Ticket.Priority.CRITICAL: "priority-critical",
}
STATUS_CHART_COLOR = {
    Ticket.Status.NOT_STARTED: "#94a3b8",
    Ticket.Status.IN_PROCESS: "#2563eb",
    Ticket.Status.ON_HOLD: "#f59e0b",
    Ticket.Status.CANNOT_COMPLETE: "#f97316",
    Ticket.Status.COMPLETED: "#16a34a",
}
PRIORITY_CHART_COLOR = {
    Ticket.Priority.LOW: "#60a5fa",
    Ticket.Priority.MEDIUM: "#94a3b8",
    Ticket.Priority.HIGH: "#f59e0b",
    Ticket.Priority.CRITICAL: "#dc2626",
}
PRIORITY_RANK = Case(
    When(priority=Ticket.Priority.CRITICAL, then=4),
    When(priority=Ticket.Priority.HIGH, then=3),
    When(priority=Ticket.Priority.MEDIUM, then=2),
    When(priority=Ticket.Priority.LOW, then=1),
    default=0,
    output_field=IntegerField(),
)
STATUS_RANK = Case(
    When(status=Ticket.Status.NOT_STARTED, then=1),
    When(status=Ticket.Status.IN_PROCESS, then=2),
    When(status=Ticket.Status.ON_HOLD, then=3),
    When(status=Ticket.Status.CANNOT_COMPLETE, then=4),
    When(status=Ticket.Status.COMPLETED, then=5),
    default=99,
    output_field=IntegerField(),
)


def get_selected_campaign(slug=None, default_to_active=False):
    queryset = Campaign.objects.order_by("name")
    if slug:
        return queryset.filter(slug=slug).first()
    if default_to_active:
        return queryset.filter(status=Campaign.Status.ACTIVE).first() or queryset.first()
    return None


def _ticket_list_url(campaign=None, scope=None, **filters):
    params = {}
    if campaign:
        params["campaign"] = campaign.pk
    if scope:
        params["scope"] = scope
    for key, value in filters.items():
        if value in (None, "", []):
            continue
        params[key] = value.pk if hasattr(value, "pk") else value
    query_string = urlencode(params)
    base_url = reverse("ticketing:list")
    return f"{base_url}?{query_string}" if query_string else base_url


def _compress_category_rows(category_rows, campaign):
    if len(category_rows) <= 6:
        return category_rows

    visible_rows = category_rows[:6]
    other_total = sum(row["count"] for row in category_rows[6:])
    visible_rows.append(
        {
            "label": "Other categories",
            "count": other_total,
            "url": _ticket_list_url(campaign),
            "color": CHART_PALETTE[6 % len(CHART_PALETTE)],
        }
    )
    return visible_rows


def get_support_dashboard_data(campaign=None):
    tickets = (
        Ticket.objects.select_related(
            "campaign",
            "department",
            "current_assignee",
            "ticket_category",
            "ticket_type_definition",
        )
        .annotate(priority_rank=PRIORITY_RANK, status_rank=STATUS_RANK)
        .order_by("-priority_rank", "status_rank", "-created_at")
    )
    if campaign:
        tickets = tickets.filter(campaign=campaign)

    completed = tickets.filter(status=Ticket.Status.COMPLETED)
    pending = tickets.exclude(status=Ticket.Status.COMPLETED)
    open_count = pending.count()
    in_progress_count = tickets.filter(status=Ticket.Status.IN_PROCESS).count()
    critical_count = tickets.filter(priority=Ticket.Priority.CRITICAL).count()
    total_count = tickets.count()
    closed_count = completed.count()

    requests_by_type = list(
        tickets.values(
            "ticket_type",
            "ticket_type_definition",
            "ticket_category__name",
            "ticket_category",
            "user_type",
            "source_system",
        )
        .annotate(total=Count("id"))
        .order_by("-total", "ticket_category__name", "ticket_type")[:10]
    )
    for row in requests_by_type:
        row["url"] = _ticket_list_url(
            campaign,
            ticket_category=row["ticket_category"],
            ticket_type_definition=row["ticket_type_definition"],
        )

    quality = defaultdict(
        lambda: {
            "ticket_type": "",
            "ticket_type_definition": None,
            "ticket_category": "",
            "ticket_category_id": None,
            "completed_count": 0,
            "average_resolution_hours": 0.0,
            "url": "",
        }
    )
    for ticket in completed:
        key = (ticket.ticket_type_definition_id or ticket.ticket_type, ticket.ticket_category_id)
        quality[key]["ticket_type"] = ticket.ticket_type
        quality[key]["ticket_type_definition"] = ticket.ticket_type_definition_id
        quality[key]["ticket_category"] = ticket.ticket_category.name if ticket.ticket_category else "Uncategorized"
        quality[key]["ticket_category_id"] = ticket.ticket_category_id
        quality[key]["completed_count"] += 1
        quality[key]["average_resolution_hours"] += ticket.resolution_hours or 0.0
        quality[key]["url"] = _ticket_list_url(
            campaign,
            status=Ticket.Status.COMPLETED,
            ticket_category=ticket.ticket_category_id,
            ticket_type_definition=ticket.ticket_type_definition_id,
        )
    quality_rows = []
    for row in quality.values():
        row["average_resolution_hours"] = round(row["average_resolution_hours"] / row["completed_count"], 2) if row["completed_count"] else 0
        quality_rows.append(row)
    quality_rows.sort(key=lambda row: (-row["completed_count"], row["ticket_category"], row["ticket_type"]))
    quality_rows = quality_rows[:8]

    pending_rows = list(
        pending.values("ticket_type", "ticket_type_definition", "ticket_category__name", "ticket_category", "campaign__name")
        .annotate(total=Count("id"))
        .order_by("-total", "ticket_category__name", "ticket_type")[:10]
    )
    pending_age = defaultdict(int)
    pending_count = defaultdict(int)
    for ticket in pending:
        key = (
            ticket.ticket_type,
            ticket.ticket_type_definition_id,
            ticket.ticket_category.name if ticket.ticket_category else "Uncategorized",
            ticket.ticket_category_id,
            ticket.campaign.name if ticket.campaign else "Unassigned",
        )
        pending_age[key] += ticket.ageing_days
        pending_count[key] += 1
    for row in pending_rows:
        key = (
            row["ticket_type"],
            row["ticket_type_definition"],
            row["ticket_category__name"] or "Uncategorized",
            row["ticket_category"],
            row["campaign__name"] or "Unassigned",
        )
        row["average_ageing_days"] = round(pending_age[key] / pending_count[key], 1) if pending_count[key] else 0
        row["url"] = _ticket_list_url(
            campaign,
            ticket_category=row["ticket_category"],
            ticket_type_definition=row["ticket_type_definition"],
        )

    high_priority_tickets = list(
        pending.filter(priority__in=[Ticket.Priority.HIGH, Ticket.Priority.CRITICAL]).order_by("-priority_rank", "status_rank", "-created_at")[:8]
    )

    status_counts = {row["status"]: row["total"] for row in tickets.values("status").annotate(total=Count("id"))}
    status_breakdown = []
    for value, label in Ticket.Status.choices:
        status_breakdown.append(
            {
                "value": value,
                "label": label,
                "count": status_counts.get(value, 0),
                "badge_class": STATUS_BADGE_CLASS.get(value, "status-secondary"),
                "url": _ticket_list_url(campaign, status=value),
            }
        )

    priority_counts = {row["priority"]: row["total"] for row in tickets.values("priority").annotate(total=Count("id"))}
    priority_breakdown = []
    for value, label in Ticket.Priority.choices:
        priority_breakdown.append(
            {
                "value": value,
                "label": label,
                "count": priority_counts.get(value, 0),
                "badge_class": PRIORITY_BADGE_CLASS.get(value, "priority-medium"),
                "url": _ticket_list_url(campaign, priority=value),
            }
        )

    raw_category_breakdown = []
    category_rows = list(
        tickets.values("ticket_category__name", "ticket_category")
        .annotate(total=Count("id"))
        .order_by("-total", "ticket_category__name")
    )
    for index, row in enumerate(category_rows):
        label = row["ticket_category__name"] or "Uncategorized"
        raw_category_breakdown.append(
            {
                "label": label,
                "count": row["total"],
                "url": _ticket_list_url(campaign, ticket_category=row["ticket_category"]) if row["ticket_category"] else _ticket_list_url(campaign),
                "color": CHART_PALETTE[index % len(CHART_PALETTE)],
            }
        )
    category_breakdown = _compress_category_rows(raw_category_breakdown, campaign)

    overview_cards = [
        {
            "label": "Total tickets",
            "value": total_count,
            "subtitle": "All tickets in current scope",
            "badge": "Overview",
            "badge_class": "status-secondary",
            "url": _ticket_list_url(campaign),
        },
        {
            "label": "Open tickets",
            "value": open_count,
            "subtitle": "Not yet completed",
            "badge": "Action",
            "badge_class": "status-warning",
            "url": _ticket_list_url(campaign, scope="open"),
        },
        {
            "label": "In progress",
            "value": in_progress_count,
            "subtitle": "Currently being worked",
            "badge": "Active",
            "badge_class": "status-info",
            "url": _ticket_list_url(campaign, scope="in_progress"),
        },
        {
            "label": "Closed",
            "value": closed_count,
            "subtitle": "Resolved or completed",
            "badge": "Stable",
            "badge_class": "status-success",
            "url": _ticket_list_url(campaign, status=Ticket.Status.COMPLETED),
        },
        {
            "label": "Critical",
            "value": critical_count,
            "subtitle": "Needs immediate response",
            "badge": "Urgent",
            "badge_class": "status-danger",
            "url": _ticket_list_url(campaign, scope="critical"),
        },
    ]

    ticket_distribution = build_ticket_distribution_data(tickets, period_days=30)
    other_issue_requests = (
        SupportRequest.objects.filter(status=SupportRequest.Status.PENDING_PM_REVIEW)
        .select_related("campaign", "support_category__super_category", "ticket_link")
        .order_by("-created_at")
    )
    if campaign:
        other_issue_requests = other_issue_requests.filter(campaign=campaign)

    other_issue_rows = [
        {
            "request": support_request,
            "raise_ticket_url": reverse("support_center:raise_ticket", kwargs={"request_id": support_request.pk}),
        }
        for support_request in other_issue_requests
    ]

    return {
        "overview_cards": overview_cards,
        "overview_tickets": tickets,
        "requests_by_type": requests_by_type,
        "quality_rows": quality_rows,
        "pending_rows": pending_rows,
        "high_priority_tickets": high_priority_tickets,
        "status_breakdown": status_breakdown,
        "priority_breakdown": priority_breakdown,
        "category_breakdown": category_breakdown,
        "ticket_distribution": ticket_distribution,
        "other_issue_rows": other_issue_rows,
        "chart_data": {
            "category": {
                "labels": [row["label"] for row in category_breakdown],
                "values": [row["count"] for row in category_breakdown],
                "urls": [row["url"] for row in category_breakdown],
                "colors": [row["color"] for row in category_breakdown],
            },
            "status": {
                "labels": [row["label"] for row in status_breakdown],
                "values": [row["count"] for row in status_breakdown],
                "urls": [row["url"] for row in status_breakdown],
                "colors": [STATUS_CHART_COLOR[row["value"]] for row in status_breakdown],
            },
            "priority": {
                "labels": [row["label"] for row in priority_breakdown],
                "values": [row["count"] for row in priority_breakdown],
                "urls": [row["url"] for row in priority_breakdown],
                "colors": [PRIORITY_CHART_COLOR[row["value"]] for row in priority_breakdown],
            },
        },
        "support_cards": {
            "total_tickets": total_count,
            "open_tickets": open_count,
            "in_progress_tickets": in_progress_count,
            "completed_tickets": closed_count,
            "critical_tickets": critical_count,
            "other_issue_requests": len(other_issue_rows),
        },
    }


def get_performance_dashboard_data(campaign=None):
    return build_live_performance_sections(campaign)


def _status_variant(code, error_message):
    if error_message:
        return "danger"
    return STATUS_COLOR_MAP.get(code, "secondary")


def _build_default_status_targets(base_url):
    normalized_base = (base_url or "").rstrip("/")
    targets = []
    if normalized_base:
        targets.extend(
            [
                {"system": "Campaign Management", "label": "Public home", "url": f"{normalized_base}/"},
                {"system": "Campaign Management", "label": "PM dashboard", "url": f"{normalized_base}/app/"},
                {"system": "Campaign Management", "label": "Ticketing", "url": f"{normalized_base}/ticketing/"},
                {"system": "Campaign Management", "label": "Campaign performance", "url": f"{normalized_base}/app/performance/"},
                {"system": "Campaign Management", "label": "Reporting contracts", "url": f"{normalized_base}/reporting/contracts/"},
            ]
        )
    targets.extend(
        [
            {"system": "Reporting APIs", "label": "Red Flag Alert feed", "url": settings.REPORTING_API_RED_FLAG_ALERT_URL},
            {"system": "Reporting APIs", "label": "In-clinic feed", "url": settings.REPORTING_API_IN_CLINIC_URL},
            {"system": "Reporting APIs", "label": "Patient Education feed", "url": settings.REPORTING_API_PATIENT_EDUCATION_URL},
            {"system": "External Sources", "label": "WordPress helper", "url": settings.WORDPRESS_HELPER_URL},
        ]
    )
    for target in getattr(settings, "STATUS_MONITOR_EXTRA_TARGETS", []):
        if isinstance(target, dict) and target.get("system") and target.get("label") and target.get("url"):
            targets.append({"system": target["system"], "label": target["label"], "url": target["url"]})
    return targets


def get_system_status_dashboard_data(base_url):
    url_rows = []
    system_summary = defaultdict(lambda: {"system": "", "ok": 0, "info": 0, "warning": 0, "critical": 0, "total": 0})
    normalized_base = (base_url or "").rstrip("/")
    internal_client = Client()

    for target in _build_default_status_targets(base_url):
        try:
            if normalized_base and target["url"].startswith(normalized_base):
                parsed = urlparse(target["url"])
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                response = internal_client.get(path, follow=False)
                status_code = response.status_code
                error_message = ""
            else:
                response = requests.get(target["url"], timeout=settings.REPORTING_API_TIMEOUT, allow_redirects=False)
                status_code = response.status_code
                error_message = ""
        except requests.RequestException as exc:
            status_code = None
            error_message = str(exc)

        variant = _status_variant(status_code, error_message)
        url_rows.append(
            {
                "system": target["system"],
                "label": target["label"],
                "url": target["url"],
                "status_code": status_code,
                "error_message": error_message,
                "variant": variant,
            }
        )

        system_summary[target["system"]]["system"] = target["system"]
        system_summary[target["system"]]["total"] += 1
        if variant == "success":
            system_summary[target["system"]]["ok"] += 1
        elif variant == "info":
            system_summary[target["system"]]["info"] += 1
        elif variant == "warning":
            system_summary[target["system"]]["warning"] += 1
        else:
            system_summary[target["system"]]["critical"] += 1

    return {
        "systems": list(system_summary.values()),
        "urls": url_rows,
    }
