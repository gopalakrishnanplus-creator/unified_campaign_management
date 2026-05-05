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


def normalized_support_token(value):
    return "".join(character for character in (value or "").lower() if character.isalnum())


def canonical_support_system(system_name, flow_name=""):
    system_name = (system_name or "").strip()
    flow_name = (flow_name or "").strip()
    system_token = normalized_support_token(system_name)
    flow_token = normalized_support_token(flow_name)
    combined_token = f"{system_token}{flow_token}"

    if system_token == "saplaicme":
        if "aicme" in flow_token:
            return "AICME"
        return "SAPL"
    if system_token == "aicme" or "aicme" in combined_token:
        return "AICME"
    if system_token == "sapl" or "sapl" in combined_token:
        return "SAPL"
    if system_token in {"inclinic", "inclinicsystem"} or "inclinic" in combined_token:
        return "In-clinic"
    if system_token in {"patienteducation", "pe"} or "patienteducation" in combined_token:
        return "Patient Education"
    if system_token in {"redflagalert", "rfa"} or "redflagalert" in combined_token:
        return "Red Flag Alert"
    if not system_name:
        return "Unknown"
    return system_name


def is_generic_support_system(system_name):
    return normalized_support_token(system_name) in {"", "unknown", "customersupport", "generalsupport", "support"}


def resolve_support_system(source_system, source_flow="", *fallback_records):
    resolved_system = canonical_support_system(source_system, source_flow)
    fallback_systems = []
    for record in fallback_records:
        if not record:
            continue
        fallback_systems.append(
            canonical_support_system(
                getattr(record, "source_system", ""),
                getattr(record, "source_flow", ""),
            )
        )

    if is_generic_support_system(resolved_system):
        for fallback_system in fallback_systems:
            if not is_generic_support_system(fallback_system):
                return fallback_system
    return resolved_system


def support_page_system(page):
    return resolve_support_system(page.source_system, page.source_flow)


def support_item_system(item):
    return resolve_support_system(item.source_system, item.source_flow, item.page)


def support_request_system(support_request):
    return resolve_support_system(support_request.source_system, support_request.source_flow, support_request.support_page)


def widget_event_system(event):
    request_page = event.support_request.support_page if event.support_request_id else None
    return resolve_support_system(event.source_system, event.source_flow, event.support_page, event.support_request, request_page)


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

    page_counts = Counter(support_page_system(page) for page in SupportPage.objects.filter(is_active=True))
    faq_counts = Counter(support_item_system(item) for item in SupportItem.objects.filter(is_active=True).select_related("page"))
    open_counts = Counter(
        widget_event_system(event)
        for event in SupportWidgetEvent.objects.filter(event_type=SupportWidgetEvent.EventType.OPENED).select_related(
            "support_page",
            "support_request",
            "support_request__support_page",
        )
    )
    resolved_counts = Counter(
        widget_event_system(event)
        for event in SupportWidgetEvent.objects.filter(event_type=SupportWidgetEvent.EventType.RESOLVED).select_related(
            "support_page",
            "support_request",
            "support_request__support_page",
        )
    )
    pm_queue_counts = Counter(
        support_request_system(support_request)
        for support_request in SupportRequest.objects.select_related("support_page")
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
    target_system = canonical_support_system(system_name)
    event_ids = [
        event.pk
        for event in SupportWidgetEvent.objects.select_related("support_page", "support_request", "support_request__support_page")
        if widget_event_system(event) == target_system
    ]
    if not event_ids:
        return 0
    deleted_count, _ = SupportWidgetEvent.objects.filter(pk__in=event_ids).delete()
    return deleted_count


def ids_for_support_system(model, system_name):
    target_system = canonical_support_system(system_name)
    if model is SupportPage:
        return [page.pk for page in SupportPage.objects.all() if support_page_system(page) == target_system]
    if model is SupportItem:
        return [item.pk for item in SupportItem.objects.select_related("page") if support_item_system(item) == target_system]
    return [
        record_id
        for record_id, source_system, source_flow in model.objects.values_list("pk", "source_system", "source_flow")
        if canonical_support_system(source_system, source_flow) == target_system
    ]


def delete_support_widgets_for_system(system_name):
    event_count = delete_widget_events_for_system(system_name)
    item_ids = ids_for_support_system(SupportItem, system_name)
    page_ids = ids_for_support_system(SupportPage, system_name)
    item_count = len(item_ids)
    page_count = len(page_ids)
    if item_ids:
        SupportItem.objects.filter(pk__in=item_ids).delete()
    if page_ids:
        SupportPage.objects.filter(pk__in=page_ids).delete()
    return {
        "event_count": event_count,
        "item_count": item_count,
        "page_count": page_count,
    }


def delete_all_support_widgets():
    event_count, _ = SupportWidgetEvent.objects.all().delete()
    item_count = SupportItem.objects.count()
    page_count = SupportPage.objects.count()
    SupportItem.objects.all().delete()
    SupportPage.objects.all().delete()
    return {
        "event_count": event_count,
        "item_count": item_count,
        "page_count": page_count,
    }


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
            "reset_all_widget_counts": self.handle_reset_all_widget_counts,
            "delete_support_widgets": self.handle_delete_support_widgets,
            "delete_all_support_widgets": self.handle_delete_all_support_widgets,
            "update_pm_request": self.handle_update_pm_request,
            "delete_pm_request": self.handle_delete_pm_request,
            "delete_selected_pm_requests": self.handle_delete_selected_pm_requests,
            "delete_all_pm_requests": self.handle_delete_all_pm_requests,
            "update_ticket": self.handle_update_ticket,
            "delete_ticket": self.handle_delete_ticket,
            "delete_selected_tickets": self.handle_delete_selected_tickets,
            "delete_all_tickets": self.handle_delete_all_tickets,
            "clear_dashboard_activity": self.handle_clear_dashboard_activity,
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
        messages.success(
            request,
            f"Reset {deleted_count} widget click event record(s) for {system_name}. "
            "FAQ pages, answers, and widget URLs are kept.",
        )
        return redirect("support_admin_dashboard")

    def handle_reset_all_widget_counts(self, request):
        deleted_count, _ = SupportWidgetEvent.objects.all().delete()
        messages.success(
            request,
            f"Reset all widget click counts by deleting {deleted_count} event record(s). "
            "FAQ pages, answers, and widget URLs are kept.",
        )
        return redirect("support_admin_dashboard")

    def handle_delete_support_widgets(self, request):
        system_name = (request.POST.get("system") or "").strip()
        if not system_name:
            messages.error(request, "Choose a system before deleting support widgets.")
            return redirect("support_admin_dashboard")
        result = delete_support_widgets_for_system(system_name)
        messages.success(
            request,
            f"Deleted support widgets for {system_name}: {result['page_count']} page(s), "
            f"{result['item_count']} FAQ item(s), and {result['event_count']} event record(s).",
        )
        return redirect("support_admin_dashboard")

    def handle_delete_all_support_widgets(self, request):
        result = delete_all_support_widgets()
        messages.success(
            request,
            f"Deleted all support widgets: {result['page_count']} page(s), "
            f"{result['item_count']} FAQ item(s), and {result['event_count']} event record(s).",
        )
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
            sync_warning = ""
            if linked_ticket:
                sync_warning = self.delete_ticket_with_external_sync(linked_ticket)
            queue_ticket_number = support_request.queue_ticket_number
            support_request.delete()
            if sync_warning:
                messages.warning(request, f"Deleted PM queue record {queue_ticket_number} locally. Internal ticket cleanup warning: {sync_warning}")
            else:
                messages.success(request, f"Deleted PM queue record {queue_ticket_number}.")
        except Exception as exc:
            messages.error(request, f"PM queue record was not deleted locally: {exc}")
        return redirect("support_admin_dashboard")

    def handle_delete_selected_pm_requests(self, request):
        selected_ids = request.POST.getlist("support_request_ids")
        if not selected_ids:
            messages.warning(request, "Select at least one PM queue record to delete.")
            return redirect("support_admin_dashboard")
        result = self.bulk_delete_pm_requests(SupportRequest.objects.filter(pk__in=selected_ids))
        self.add_bulk_delete_message(
            request,
            "Selected PM queue",
            f"Deleted {result['deleted_requests']} PM queue record(s) and {result['deleted_linked_tickets']} linked ticket(s).",
            result["failures"],
        )
        return redirect("support_admin_dashboard")

    def handle_delete_all_pm_requests(self, request):
        result = self.bulk_delete_pm_requests(SupportRequest.objects.all())
        self.add_bulk_delete_message(
            request,
            "PM queue",
            f"Deleted {result['deleted_requests']} PM queue record(s) and {result['deleted_linked_tickets']} linked ticket(s).",
            result["failures"],
        )
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
            sync_warning = self.delete_ticket_with_external_sync(ticket)
        except Exception as exc:
            messages.error(request, f"Ticket was not deleted locally: {exc}")
            return redirect("support_admin_dashboard")
        if sync_warning:
            messages.warning(request, f"Deleted ticket {ticket.ticket_number} locally. Internal ticket cleanup warning: {sync_warning}")
        else:
            messages.success(request, f"Deleted ticket {ticket.ticket_number}.")
        return redirect("support_admin_dashboard")

    def handle_delete_selected_tickets(self, request):
        selected_ids = request.POST.getlist("ticket_ids")
        if not selected_ids:
            messages.warning(request, "Select at least one ticket record to delete.")
            return redirect("support_admin_dashboard")
        result = self.bulk_delete_tickets(Ticket.objects.filter(pk__in=selected_ids))
        self.add_bulk_delete_message(
            request,
            "Selected tickets",
            f"Deleted {result['deleted']} ticket record(s).",
            result["failures"],
        )
        return redirect("support_admin_dashboard")

    def handle_delete_all_tickets(self, request):
        result = self.bulk_delete_tickets(Ticket.objects.all())
        self.add_bulk_delete_message(
            request,
            "Ticketing data",
            f"Deleted {result['deleted']} ticket record(s).",
            result["failures"],
        )
        return redirect("support_admin_dashboard")

    def handle_clear_dashboard_activity(self, request):
        ticket_result = self.bulk_delete_tickets(Ticket.objects.all())
        pm_result = self.bulk_delete_pm_requests(SupportRequest.objects.all())
        widget_deleted_count, _ = SupportWidgetEvent.objects.all().delete()
        failure_count = len(ticket_result["failures"]) + len(pm_result["failures"])
        summary = (
            f"Cleared {widget_deleted_count} widget event record(s), "
            f"{pm_result['deleted_requests']} PM queue record(s), "
            f"and {ticket_result['deleted'] + pm_result['deleted_linked_tickets']} ticket record(s)."
        )
        if failure_count:
            messages.warning(
                request,
                f"{summary} Internal ticket cleanup had {failure_count} warning(s): "
                + self.format_failure_preview([*ticket_result["failures"], *pm_result["failures"]]),
            )
        else:
            messages.success(request, summary)
        return redirect("support_admin_dashboard")

    @staticmethod
    def delete_ticket_with_external_sync(ticket):
        sync_warning = ""
        if ticket.external_ticket_number:
            try:
                delete_external_ticket(
                    ticket,
                    actor_email=settings.PROJECT_MANAGER_EMAIL,
                    message="Ticket deleted from Campaign Management admin dashboard.",
                )
            except Exception as exc:
                sync_warning = f"{ticket.ticket_number}: {exc}"
        ticket.delete()
        return sync_warning

    def bulk_delete_tickets(self, queryset):
        deleted_count = 0
        failures = []
        tickets = list(
            queryset.select_related("current_assignee", "submitted_by", "created_by", "support_request").order_by("pk")
        )
        for ticket in tickets:
            ticket_number = ticket.ticket_number
            try:
                sync_warning = self.delete_ticket_with_external_sync(ticket)
                deleted_count += 1
                if sync_warning:
                    failures.append(sync_warning)
            except Exception as exc:
                failures.append(f"{ticket_number}: local deletion failed: {exc}")
        return {
            "deleted": deleted_count,
            "failures": failures,
        }

    def bulk_delete_pm_requests(self, queryset):
        deleted_requests = 0
        deleted_linked_tickets = 0
        failures = []
        support_requests = list(queryset.order_by("pk"))
        for support_request in support_requests:
            queue_ticket_number = support_request.queue_ticket_number
            linked_ticket = (
                Ticket.objects.filter(support_request=support_request)
                .select_related("current_assignee", "submitted_by", "created_by")
                .first()
            )
            try:
                if linked_ticket:
                    sync_warning = self.delete_ticket_with_external_sync(linked_ticket)
                    deleted_linked_tickets += 1
                    if sync_warning:
                        failures.append(sync_warning)
                support_request.delete()
                deleted_requests += 1
            except Exception as exc:
                failures.append(f"{queue_ticket_number}: local deletion failed: {exc}")
        return {
            "deleted_requests": deleted_requests,
            "deleted_linked_tickets": deleted_linked_tickets,
            "failures": failures,
        }

    @staticmethod
    def format_failure_preview(failures):
        preview = "; ".join(failures[:3])
        if len(failures) > 3:
            preview = f"{preview}; and {len(failures) - 3} more"
        return preview

    def add_bulk_delete_message(self, request, label, success_message, failures):
        if failures:
            messages.warning(
                request,
                f"{label}: {success_message} Internal ticket cleanup had {len(failures)} warning(s): "
                + self.format_failure_preview(failures),
            )
            return
        messages.success(request, f"{label}: {success_message}")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pm_request_total = SupportRequest.objects.count()
        ticket_total = Ticket.objects.count()
        widget_event_total = SupportWidgetEvent.objects.count()
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
                "pm_request_total": pm_request_total,
                "ticket_total": ticket_total,
                "widget_event_total": widget_event_total,
                "external_sync_enabled": settings.EXTERNAL_TICKETING_SYNC_ENABLED,
                "external_base_url": settings.EXTERNAL_TICKETING_BASE_URL,
                "admin_username": ADMIN_DASHBOARD_USERNAME,
                "admin_dashboard_path": "/" + ADMIN_DASHBOARD_PATH,
            }
        )
        return context
