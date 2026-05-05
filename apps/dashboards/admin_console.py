from collections import Counter

from django import forms
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.views.generic import TemplateView, View

from apps.support_center.models import SupportItem, SupportPage, SupportRequest, SupportWidgetEvent
from apps.ticketing.external_ticketing import (
    delete_external_ticket,
    update_external_ticket_from_local,
)
from apps.ticketing.models import Department, Ticket


ADMIN_DASHBOARD_SESSION_KEY = "support_admin_dashboard_authenticated"
ADMIN_DASHBOARD_USERNAME = "inditech-admin"
ADMIN_DASHBOARD_PASSWORD = "Inditech@2026"
ADMIN_DASHBOARD_LOGIN_PATH = "__support-admin__/login/"
ADMIN_DASHBOARD_PATH = "__support-admin__/"


class SupportRequestAdminForm(forms.ModelForm):
    class Meta:
        model = SupportRequest
        fields = [
            "status",
            "is_escalated",
            "source_system",
            "source_flow",
            "subject",
            "free_text",
            "requester_name",
            "requester_email",
            "requester_number",
            "requester_company",
        ]


class TicketAdminForm(forms.ModelForm):
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True).select_related("default_recipient").order_by("name"),
    )

    class Meta:
        model = Ticket
        fields = [
            "title",
            "description",
            "status",
            "priority",
            "is_escalated",
            "department",
            "requester_name",
            "requester_email",
            "requester_number",
            "requester_company",
        ]

    def clean_department(self):
        department = self.cleaned_data["department"]
        if not department.default_recipient_id:
            raise forms.ValidationError("Selected department does not have an auto-assigned manager.")
        return department

    def save(self, commit=True):
        ticket = super().save(commit=False)
        if "department" in self.changed_data:
            ticket.direct_recipient = ticket.department.default_recipient
            ticket.current_assignee = ticket.department.default_recipient
        if commit:
            ticket.save()
        return ticket


def admin_dashboard_authenticated(request):
    return bool(request.session.get(ADMIN_DASHBOARD_SESSION_KEY))


def canonical_support_system(system_name, flow_name=""):
    system_name = (system_name or "").strip()
    flow_name = (flow_name or "").strip()
    if not system_name:
        return "Unknown"
    if system_name != "SAPLAICME":
        return system_name
    normalized_flow = flow_name.replace("-", "").replace("_", "").replace(" ", "").lower()
    if "aicme" in normalized_flow:
        return "AICME"
    return "SAPL"


def ticket_source_label(source_system):
    return dict(Ticket.SourceSystem.choices).get(source_system, source_system or "Unknown")


def empty_system_row(system_name):
    return {
        "system": system_name,
        "page_count": 0,
        "faq_count": 0,
        "widget_open_count": 0,
        "resolved_count": 0,
        "pm_queue_count": 0,
        "ticket_count": 0,
    }


def build_support_widget_count_rows():
    rows = {}

    def row_for(system_name):
        if system_name not in rows:
            rows[system_name] = empty_system_row(system_name)
        return rows[system_name]

    page_counts = Counter(
        canonical_support_system(source_system, source_flow)
        for source_system, source_flow in SupportPage.objects.filter(is_active=True).values_list("source_system", "source_flow")
    )
    faq_counts = Counter(
        canonical_support_system(source_system, source_flow)
        for source_system, source_flow in SupportItem.objects.filter(is_active=True).values_list("source_system", "source_flow")
    )
    open_counts = Counter(
        canonical_support_system(source_system, source_flow)
        for source_system, source_flow in SupportWidgetEvent.objects.filter(event_type=SupportWidgetEvent.EventType.OPENED).values_list(
            "source_system",
            "source_flow",
        )
    )
    resolved_counts = Counter(
        canonical_support_system(source_system, source_flow)
        for source_system, source_flow in SupportWidgetEvent.objects.filter(event_type=SupportWidgetEvent.EventType.RESOLVED).values_list(
            "source_system",
            "source_flow",
        )
    )
    pm_queue_counts = Counter(
        canonical_support_system(source_system, source_flow)
        for source_system, source_flow in SupportRequest.objects.all().values_list("source_system", "source_flow")
    )
    ticket_counts = Counter(ticket_source_label(source_system) for source_system in Ticket.objects.all().values_list("source_system", flat=True))

    for counter, key in [
        (page_counts, "page_count"),
        (faq_counts, "faq_count"),
        (open_counts, "widget_open_count"),
        (resolved_counts, "resolved_count"),
        (pm_queue_counts, "pm_queue_count"),
        (ticket_counts, "ticket_count"),
    ]:
        for system_name, count in counter.items():
            row_for(system_name)[key] = count

    return sorted(rows.values(), key=lambda row: (row["system"] == "Unknown", row["system"].lower()))


def delete_widget_events_for_system(system_name):
    event_ids = [
        event_id
        for event_id, source_system, source_flow in SupportWidgetEvent.objects.values_list("pk", "source_system", "source_flow")
        if canonical_support_system(source_system, source_flow) == system_name
    ]
    if not event_ids:
        return 0
    deleted_count, _ = SupportWidgetEvent.objects.filter(pk__in=event_ids).delete()
    return deleted_count


class AdminDashboardAuthMixin:
    def dispatch(self, request, *args, **kwargs):
        if not admin_dashboard_authenticated(request):
            login_url = reverse("support_admin_login")
            return redirect(f"{login_url}?next={request.get_full_path()}")
        return super().dispatch(request, *args, **kwargs)


class AdminDashboardLoginView(TemplateView):
    template_name = "dashboards/admin_login.jinja"
    template_engine = "jinja2"

    def get(self, request, *args, **kwargs):
        if admin_dashboard_authenticated(request):
            return redirect("support_admin_dashboard")
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        if constant_time_compare(username, ADMIN_DASHBOARD_USERNAME) and constant_time_compare(password, ADMIN_DASHBOARD_PASSWORD):
            request.session[ADMIN_DASHBOARD_SESSION_KEY] = True
            request.session.cycle_key()
            return redirect(request.POST.get("next") or "support_admin_dashboard")
        messages.error(request, "Invalid admin dashboard credentials.")
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next_url"] = self.request.GET.get("next") or self.request.POST.get("next") or reverse("support_admin_dashboard")
        return context


class AdminDashboardLogoutView(View):
    def post(self, request, *args, **kwargs):
        request.session.pop(ADMIN_DASHBOARD_SESSION_KEY, None)
        messages.success(request, "Admin dashboard session ended.")
        return redirect("support_admin_login")


class AdminDashboardView(AdminDashboardAuthMixin, TemplateView):
    template_name = "dashboards/admin_dashboard.jinja"
    template_engine = "jinja2"

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        handlers = {
            "reset_widget_counts": self.handle_reset_widget_counts,
            "update_pm_request": self.handle_update_pm_request,
            "delete_pm_request": self.handle_delete_pm_request,
            "update_ticket": self.handle_update_ticket,
            "delete_ticket": self.handle_delete_ticket,
        }
        handler = handlers.get(action)
        if not handler:
            messages.error(request, "Unknown admin dashboard action.")
            return redirect("support_admin_dashboard")
        return handler(request)

    def handle_reset_widget_counts(self, request):
        system_name = (request.POST.get("system") or "").strip()
        if not system_name:
            messages.error(request, "Choose a system before resetting widget counts.")
            return redirect("support_admin_dashboard")
        deleted_count = delete_widget_events_for_system(system_name)
        messages.success(request, f"Reset {deleted_count} widget event record(s) for {system_name}.")
        return redirect("support_admin_dashboard")

    def handle_update_pm_request(self, request):
        support_request = get_object_or_404(SupportRequest, pk=request.POST.get("support_request_id"))
        form = SupportRequestAdminForm(request.POST, instance=support_request)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated PM queue record {support_request.queue_ticket_number}.")
        else:
            messages.error(request, "PM queue record update failed: " + "; ".join(form.errors.get_json_data().keys()))
        return redirect("support_admin_dashboard")

    def handle_delete_pm_request(self, request):
        support_request = get_object_or_404(SupportRequest, pk=request.POST.get("support_request_id"))
        linked_ticket = Ticket.objects.filter(support_request=support_request).select_related("current_assignee", "submitted_by", "created_by").first()
        try:
            if linked_ticket:
                self.delete_ticket_with_external_sync(linked_ticket)
            queue_ticket_number = support_request.queue_ticket_number
            support_request.delete()
            messages.success(request, f"Deleted PM queue record {queue_ticket_number}.")
        except Exception as exc:
            messages.error(request, f"PM queue record was not deleted because linked internal ticket deletion failed: {exc}")
        return redirect("support_admin_dashboard")

    def handle_update_ticket(self, request):
        ticket = get_object_or_404(
            Ticket.objects.select_related("department", "current_assignee", "direct_recipient", "submitted_by", "created_by"),
            pk=request.POST.get("ticket_id"),
        )
        form = TicketAdminForm(request.POST, instance=ticket)
        if not form.is_valid():
            messages.error(request, "Ticket update failed: " + "; ".join(form.errors.get_json_data().keys()))
            return redirect("support_admin_dashboard")

        ticket = form.save()
        if ticket.external_ticket_number:
            try:
                update_external_ticket_from_local(ticket, message="Ticket updated from Campaign Management admin dashboard.")
            except Exception as exc:
                messages.warning(request, f"Local ticket updated, but internal ticket sync failed: {exc}")
                return redirect("support_admin_dashboard")
        messages.success(request, f"Updated ticket {ticket.ticket_number}.")
        return redirect("support_admin_dashboard")

    def handle_delete_ticket(self, request):
        ticket = get_object_or_404(
            Ticket.objects.select_related("current_assignee", "submitted_by", "created_by"),
            pk=request.POST.get("ticket_id"),
        )
        try:
            self.delete_ticket_with_external_sync(ticket)
        except Exception as exc:
            messages.error(request, f"Ticket was not deleted because internal ticket deletion failed: {exc}")
            return redirect("support_admin_dashboard")
        messages.success(request, f"Deleted ticket {ticket.ticket_number}.")
        return redirect("support_admin_dashboard")

    @staticmethod
    def delete_ticket_with_external_sync(ticket):
        if ticket.external_ticket_number:
            delete_external_ticket(
                ticket,
                actor_email=settings.PROJECT_MANAGER_EMAIL,
                message="Ticket deleted from Campaign Management admin dashboard.",
            )
        ticket.delete()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pm_requests = (
            SupportRequest.objects.select_related("support_page", "support_super_category", "support_category", "campaign")
            .order_by("-is_escalated", "-created_at")[:75]
        )
        tickets = (
            Ticket.objects.select_related(
                "department",
                "department__default_recipient",
                "current_assignee",
                "support_request",
                "ticket_category",
                "ticket_type_definition",
            )
            .order_by("-is_escalated", "-created_at")[:75]
        )
        context.update(
            {
                "widget_count_rows": build_support_widget_count_rows(),
                "pm_requests": pm_requests,
                "tickets": tickets,
                "support_request_status_choices": SupportRequest.Status.choices,
                "ticket_status_choices": Ticket.Status.choices,
                "ticket_priority_choices": Ticket.Priority.choices,
                "departments": Department.objects.filter(is_active=True).select_related("default_recipient").order_by("name"),
                "external_sync_enabled": settings.EXTERNAL_TICKETING_SYNC_ENABLED,
                "external_base_url": settings.EXTERNAL_TICKETING_BASE_URL,
                "admin_username": ADMIN_DASHBOARD_USERNAME,
                "admin_dashboard_path": "/" + ADMIN_DASHBOARD_PATH,
            }
        )
        return context
