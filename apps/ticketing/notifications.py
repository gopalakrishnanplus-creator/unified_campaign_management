import logging

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


logger = logging.getLogger(__name__)


def _send_email_via_sendgrid(*, to_emails, subject, text_body, html_body):
    response = requests.post(
        settings.SENDGRID_API_URL,
        headers={
            "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "personalizations": [
                {
                    "to": [{"email": email} for email in to_emails],
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


def _send_email_via_django(*, to_emails, subject, text_body, html_body):
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to_emails,
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)


def escalation_recipient_emails(ticket):
    recipients = []
    for email in (
        ticket.department.support_email,
        ticket.department.external_manager_email,
        getattr(ticket.direct_recipient, "email", ""),
        getattr(ticket.current_assignee, "email", ""),
    ):
        email = (email or "").strip().lower()
        if email and email not in recipients:
            recipients.append(email)
    return recipients


def send_ticket_escalation_email(ticket, actor):
    recipients = escalation_recipient_emails(ticket)
    if not recipients:
        return

    context = {
        "ticket": ticket,
        "actor": actor,
        "recipients": recipients,
    }
    subject = f"Critical escalation: {ticket.ticket_number} / {ticket.title}"
    text_body = render_to_string("ticketing/emails/ticket_escalation.txt", context)
    html_body = render_to_string("ticketing/emails/ticket_escalation.html", context)

    try:
        if settings.SENDGRID_API_KEY:
            _send_email_via_sendgrid(
                to_emails=recipients,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )
        else:
            _send_email_via_django(
                to_emails=recipients,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )
    except Exception:
        logger.exception("Ticket escalation email failed for %s", ticket.ticket_number)
