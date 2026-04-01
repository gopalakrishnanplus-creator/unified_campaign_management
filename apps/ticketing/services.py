from django.db import transaction

from .models import Ticket, TicketRoutingEvent


@transaction.atomic
def create_ticket(**kwargs):
    ticket = Ticket.objects.create(**kwargs)
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
