from collections import defaultdict

from django.db.models import Count

from apps.campaigns.models import Campaign
from apps.reporting.services import build_live_performance_sections
from apps.ticketing.models import Ticket


def get_selected_campaign(slug=None):
    queryset = Campaign.objects.order_by("name")
    if slug:
        return queryset.filter(slug=slug).first()
    return queryset.filter(status=Campaign.Status.ACTIVE).first() or queryset.first()


def get_support_dashboard_data(campaign=None):
    tickets = Ticket.objects.select_related("campaign")
    if campaign:
        tickets = tickets.filter(campaign=campaign)

    requests_by_type = list(
        tickets.values("ticket_type", "user_type", "source_system", "campaign__name")
        .annotate(total=Count("id"))
        .order_by("-total", "ticket_type")
    )

    completed = tickets.filter(status=Ticket.Status.COMPLETED)
    quality = defaultdict(lambda: {"ticket_type": "", "completed_count": 0, "average_resolution_hours": 0.0})
    for ticket in completed:
        key = ticket.ticket_type
        quality[key]["ticket_type"] = key
        quality[key]["completed_count"] += 1
        quality[key]["average_resolution_hours"] += ticket.resolution_hours or 0.0
    quality_rows = []
    for row in quality.values():
        row["average_resolution_hours"] = round(row["average_resolution_hours"] / row["completed_count"], 2) if row["completed_count"] else 0
        quality_rows.append(row)
    quality_rows.sort(key=lambda row: (-row["completed_count"], row["ticket_type"]))

    pending = tickets.exclude(status=Ticket.Status.COMPLETED)
    pending_rows = list(
        pending.values("ticket_type", "campaign__name")
        .annotate(total=Count("id"))
        .order_by("-total", "ticket_type")
    )
    pending_age = defaultdict(int)
    pending_count = defaultdict(int)
    for ticket in pending:
        key = (ticket.ticket_type, ticket.campaign.name if ticket.campaign else "Unassigned")
        pending_age[key] += ticket.ageing_days
        pending_count[key] += 1
    for row in pending_rows:
        key = (row["ticket_type"], row["campaign__name"] or "Unassigned")
        row["average_ageing_days"] = round(pending_age[key] / pending_count[key], 1) if pending_count[key] else 0

    return {
        "requests_by_type": requests_by_type,
        "quality_rows": quality_rows,
        "pending_rows": pending_rows,
        "support_cards": {
            "total_tickets": tickets.count(),
            "open_tickets": pending.count(),
            "completed_tickets": completed.count(),
            "critical_tickets": tickets.filter(priority=Ticket.Priority.CRITICAL).count(),
        },
    }

def get_performance_dashboard_data(campaign=None):
    return build_live_performance_sections(campaign)
