from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.db.models import Case, IntegerField, Q, When
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from .forms import (
    TicketCreateForm,
    TicketDelegationForm,
    TicketDistributionFilterForm,
    TicketFilterForm,
    TicketNoteForm,
    TicketStatusForm,
)
from .models import Department, Ticket, TicketTypeDefinition
from .services import (
    build_ticket_distribution_data,
    build_ticket_priority_summary,
    change_ticket_status,
    create_ticket,
    delegate_ticket,
    return_ticket_to_sender,
)
from .external_ticketing import (
    ExternalTicketingSyncError,
    external_ticketing_enabled,
    should_sync_external_ticket,
    sync_external_directory,
    sync_external_ticket,
    sync_external_ticket_state,
    sync_external_ticket_states,
    sync_external_ticket_attachments,
)


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


def _scoped_ticket_queryset(request):
    queryset = Ticket.objects.select_related(
        "campaign",
        "department",
        "direct_recipient",
        "current_assignee",
        "ticket_category",
        "ticket_type_definition",
    ).annotate(
        priority_rank=PRIORITY_RANK,
        status_rank=STATUS_RANK,
    )
    user = request.user
    if not (user.is_superuser or user.is_project_manager):
        queryset = queryset.filter(Q(direct_recipient=user) | Q(current_assignee=user) | Q(created_by=user))
    return queryset


class TicketListView(LoginRequiredMixin, ListView):
    model = Ticket
    template_name = "ticketing/list.jinja"
    template_engine = "jinja2"
    context_object_name = "tickets"
    paginate_by = 25

    def get_queryset(self):
        queryset = _scoped_ticket_queryset(self.request)
        if self.request.user.is_superuser or self.request.user.is_project_manager:
            sync_external_ticket_states(queryset)
        scope = self.request.GET.get("scope")
        query = self.request.GET.get("query")
        status = self.request.GET.get("status")
        priority = self.request.GET.get("priority")
        ticket_category = self.request.GET.get("ticket_category")
        ticket_type_definition = self.request.GET.get("ticket_type_definition")
        period_days = self.request.GET.get("period_days")
        sort_by = self.request.GET.get("sort_by") or "newest"

        if scope == "open":
            queryset = queryset.exclude(status=Ticket.Status.COMPLETED)
        elif scope == "in_progress":
            queryset = queryset.filter(status=Ticket.Status.IN_PROCESS)
        elif scope == "closed":
            queryset = queryset.filter(status=Ticket.Status.COMPLETED)
        elif scope == "critical":
            queryset = queryset.filter(priority=Ticket.Priority.CRITICAL)
        elif scope == "stalled":
            queryset = queryset.filter(
                status__in=[Ticket.Status.NOT_STARTED, Ticket.Status.ON_HOLD, Ticket.Status.CANNOT_COMPLETE]
            )

        if query:
            queryset = queryset.filter(
                Q(ticket_number__icontains=query)
                | Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(requester_name__icontains=query)
                | Q(requester_email__icontains=query)
            )
        if status:
            queryset = queryset.filter(status=status)
        if priority:
            queryset = queryset.filter(priority=priority)
        if ticket_category:
            queryset = queryset.filter(ticket_category_id=ticket_category)
        if ticket_type_definition:
            queryset = queryset.filter(ticket_type_definition_id=ticket_type_definition)
        if period_days:
            queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=int(period_days)))
        if sort_by == "oldest":
            return queryset.order_by("created_at")
        if sort_by == "priority_desc":
            return queryset.order_by("-priority_rank", "status_rank", "-created_at")
        if sort_by == "status":
            return queryset.order_by("status_rank", "-priority_rank", "-created_at")
        if sort_by == "updated":
            return queryset.order_by("-updated_at", "-created_at")
        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = TicketFilterForm(self.request.GET or None)
        context["priority_summary"] = build_ticket_priority_summary(self.object_list)
        context["active_scope"] = self.request.GET.get("scope", "")
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        encoded = query_params.urlencode()
        context["page_query_prefix"] = f"{encoded}&" if encoded else ""
        return context


class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    form_class = TicketCreateForm
    template_name = "ticketing/create.jinja"
    template_engine = "jinja2"

    def dispatch(self, request, *args, **kwargs):
        self.synced_departments = None
        if external_ticketing_enabled():
            try:
                self.synced_departments = sync_external_directory()
                if not self.synced_departments:
                    messages.warning(
                        request,
                        "No departments were returned from the internal ticketing directory. Ticket routing may be unavailable until that API is populated.",
                    )
            except ExternalTicketingSyncError as exc:
                messages.warning(
                    request,
                    f"Internal ticketing directory sync could not be refreshed right now: {exc}",
                )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        if self.synced_departments is not None:
            synced_ids = [department.pk for department in self.synced_departments]
            kwargs["departments"] = Department.objects.filter(pk__in=synced_ids, is_active=True).select_related("default_recipient").order_by("name")
        return kwargs

    def form_valid(self, form):
        department = form.cleaned_data["department"]
        if not department.default_recipient:
            messages.error(self.request, "This department does not have a default recipient configured yet.")
            return self.form_invalid(form)

        ticket_type_definition = form.cleaned_data.get("ticket_type_definition")
        if ticket_type_definition and ticket_type_definition.default_department_id and ticket_type_definition.default_department_id != department.id:
            messages.warning(
                self.request,
                "Selected ticket type is normally routed to a different department. Proceeding with the chosen department.",
            )
        payload = {
            key: value
            for key, value in form.cleaned_data.items()
            if key not in {"ticket_category", "ticket_type_definition", "new_ticket_type_name"}
        }
        ticket = create_ticket(
            created_by=self.request.user,
            submitted_by=self.request.user,
            ticket_category=form.cleaned_data["ticket_category"],
            ticket_type_definition=ticket_type_definition,
            new_ticket_type_name=form.cleaned_data.get("new_ticket_type_name"),
            **payload,
        )
        ticket.refresh_from_db()
        if ticket.external_ticket_number:
            messages.success(
                self.request,
                f"Ticket {ticket.ticket_number} created and mirrored to internal ticket {ticket.external_ticket_number}.",
            )
        elif settings.EXTERNAL_TICKETING_SYNC_ENABLED and ticket.external_ticket_error:
            messages.warning(
                self.request,
                f"Ticket {ticket.ticket_number} created, but internal sync failed: {ticket.external_ticket_error}",
            )
        else:
            messages.success(self.request, f"Ticket {ticket.ticket_number} created.")
        return redirect("ticketing:detail", pk=ticket.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ticket_types = TicketTypeDefinition.objects.filter(is_active=True).select_related("category").order_by("category__name", "name")
        context["ticket_types_payload"] = [
            {"id": ticket_type.id, "category_id": ticket_type.category_id, "name": ticket_type.name}
            for ticket_type in ticket_types
        ]
        return context


class TicketDetailView(LoginRequiredMixin, DetailView):
    model = Ticket
    template_name = "ticketing/detail.jinja"
    template_engine = "jinja2"
    context_object_name = "ticket"

    def get_object(self, queryset=None):
        ticket = get_object_or_404(
            Ticket.objects.select_related(
                "campaign",
                "department",
                "direct_recipient",
                "current_assignee",
                "created_by",
                "ticket_category",
                "ticket_type_definition",
            ),
            pk=self.kwargs["pk"],
        )
        if not ticket.can_view(self.request.user):
            raise PermissionDenied("You do not have access to this ticket.")
        return ticket

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_externally_managed:
            sync_external_ticket_state(self.object.pk)
            self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        action = request.POST.get("action")
        if action == "status":
            return self.handle_status_change()
        if action == "delegate":
            return self.handle_delegate()
        if action == "return":
            return self.handle_return()
        if action == "note":
            return self.handle_note()
        messages.error(request, "Unknown ticket action.")
        return redirect("ticketing:detail", pk=self.object.pk)

    def handle_status_change(self):
        if self.object.is_externally_managed:
            messages.info(
                self.request,
                "Status changes are managed in the Inditech ticketing system for mirrored tickets.",
            )
            return redirect("ticketing:detail", pk=self.object.pk)
        if not self.object.can_change_status(self.request.user):
            messages.error(self.request, "Only the direct recipient can change ticket status.")
            return redirect("ticketing:detail", pk=self.object.pk)
        form = TicketStatusForm(self.request.POST, instance=self.object)
        if form.is_valid():
            change_ticket_status(self.object, self.request.user, form.cleaned_data["status"])
            messages.success(self.request, "Ticket status updated.")
        else:
            messages.error(self.request, "Ticket status update failed.")
        return redirect("ticketing:detail", pk=self.object.pk)

    def handle_delegate(self):
        if self.object.is_externally_managed:
            messages.info(
                self.request,
                "Delegation is managed in the Inditech ticketing system for mirrored tickets.",
            )
            return redirect("ticketing:detail", pk=self.object.pk)
        if self.request.user != self.object.current_assignee and not self.request.user.is_superuser:
            messages.error(self.request, "Only the current assignee can delegate this ticket.")
            return redirect("ticketing:detail", pk=self.object.pk)
        form = TicketDelegationForm(self.request.POST, user=self.request.user)
        if form.is_valid():
            delegate_ticket(self.object, self.request.user, form.cleaned_data["assignee"])
            messages.success(self.request, "Ticket delegated.")
        else:
            messages.error(self.request, "Ticket delegation failed.")
        return redirect("ticketing:detail", pk=self.object.pk)

    def handle_return(self):
        if self.object.is_externally_managed:
            messages.info(
                self.request,
                "Assignment changes are managed in the Inditech ticketing system for mirrored tickets.",
            )
            return redirect("ticketing:detail", pk=self.object.pk)
        if self.request.user != self.object.current_assignee and not self.request.user.is_superuser:
            messages.error(self.request, "Only the current assignee can return this ticket.")
            return redirect("ticketing:detail", pk=self.object.pk)
        if not self.object.created_by:
            messages.error(self.request, "This ticket does not have a sender to return to.")
            return redirect("ticketing:detail", pk=self.object.pk)
        return_ticket_to_sender(self.object, self.request.user)
        messages.success(self.request, "Ticket returned to sender.")
        return redirect("ticketing:detail", pk=self.object.pk)

    def handle_note(self):
        form = TicketNoteForm(self.request.POST, self.request.FILES)
        if form.is_valid():
            note = form.save(commit=False)
            note.ticket = self.object
            note.author = self.request.user
            note.save()
            attachments = form.save_attachments(note)
            if attachments and external_ticketing_enabled():
                attachment_ids = [attachment.pk for attachment in attachments]
                if self.object.external_ticket_number:
                    sync_external_ticket_attachments(self.object.pk, attachment_ids=attachment_ids)
                elif should_sync_external_ticket(self.object):
                    sync_external_ticket(self.object.pk)
            messages.success(self.request, "Note added to ticket.")
        else:
            messages.error(self.request, "Note could not be saved.")
        return redirect("ticketing:detail", pk=self.object.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ticket_management_locked"] = self.object.is_externally_managed
        if not self.object.is_externally_managed:
            context["status_form"] = TicketStatusForm(instance=self.object)
            context["delegation_form"] = TicketDelegationForm(user=self.request.user)
        context["note_form"] = TicketNoteForm()
        return context


class TicketDistributionView(LoginRequiredMixin, TemplateView):
    template_name = "ticketing/distribution.jinja"
    template_engine = "jinja2"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = TicketDistributionFilterForm(self.request.GET or None)
        queryset = _scoped_ticket_queryset(self.request)
        if form.is_valid():
            category = form.cleaned_data.get("ticket_category")
            ticket_type_definition = form.cleaned_data.get("ticket_type_definition")
            source_system = form.cleaned_data.get("source_system")
            period_days = int(form.cleaned_data.get("period_days") or 30)
            if category:
                queryset = queryset.filter(ticket_category=category)
            if ticket_type_definition:
                queryset = queryset.filter(ticket_type_definition=ticket_type_definition)
            if source_system:
                queryset = queryset.filter(source_system=source_system)
        else:
            period_days = 30

        distribution = build_ticket_distribution_data(queryset, period_days=period_days)
        context.update(
            {
                "filter_form": form,
                "distribution_data": distribution,
                "distribution_chart_data": {
                    "labels": distribution["labels"],
                    "totals": distribution["totals"],
                    "by_category": distribution["by_category"],
                },
                "period_days": period_days,
            }
        )
        return context
