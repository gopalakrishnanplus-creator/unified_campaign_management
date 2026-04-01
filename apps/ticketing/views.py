from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView

from .forms import TicketCreateForm, TicketDelegationForm, TicketFilterForm, TicketNoteForm, TicketStatusForm
from .models import Ticket
from .services import change_ticket_status, create_ticket, delegate_ticket, return_ticket_to_sender


class TicketListView(LoginRequiredMixin, ListView):
    model = Ticket
    template_name = "ticketing/list.jinja"
    template_engine = "jinja2"
    context_object_name = "tickets"
    paginate_by = 25

    def get_queryset(self):
        queryset = Ticket.objects.select_related("campaign", "department", "direct_recipient", "current_assignee")
        user = self.request.user
        if not (user.is_superuser or user.is_project_manager):
            queryset = queryset.filter(Q(direct_recipient=user) | Q(current_assignee=user) | Q(created_by=user))

        status = self.request.GET.get("status")
        campaign = self.request.GET.get("campaign")
        period_days = self.request.GET.get("period_days")
        if status:
            queryset = queryset.filter(status=status)
        if campaign:
            queryset = queryset.filter(campaign_id=campaign)
        if period_days:
            queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=int(period_days)))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = TicketFilterForm(self.request.GET or None)
        return context


class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    form_class = TicketCreateForm
    template_name = "ticketing/create.jinja"
    template_engine = "jinja2"

    def form_valid(self, form):
        department = form.cleaned_data["department"]
        if not department.default_recipient:
            messages.error(self.request, "This department does not have a default recipient configured yet.")
            return self.form_invalid(form)
        ticket = create_ticket(
            created_by=self.request.user,
            submitted_by=self.request.user,
            direct_recipient=department.default_recipient,
            current_assignee=department.default_recipient,
            **form.cleaned_data,
        )
        messages.success(self.request, f"Ticket {ticket.ticket_number} created.")
        return redirect("ticketing:detail", pk=ticket.pk)


class TicketDetailView(LoginRequiredMixin, DetailView):
    model = Ticket
    template_name = "ticketing/detail.jinja"
    template_engine = "jinja2"
    context_object_name = "ticket"

    def get_object(self, queryset=None):
        ticket = get_object_or_404(
            Ticket.objects.select_related("campaign", "department", "direct_recipient", "current_assignee", "created_by"),
            pk=self.kwargs["pk"],
        )
        if not ticket.can_view(self.request.user):
            raise PermissionDenied("You do not have access to this ticket.")
        return ticket

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
            form.save_attachments(note)
            messages.success(self.request, "Note added to ticket.")
        else:
            messages.error(self.request, "Note could not be saved.")
        return redirect("ticketing:detail", pk=self.object.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_form"] = TicketStatusForm(instance=self.object)
        context["delegation_form"] = TicketDelegationForm(user=self.request.user)
        context["note_form"] = TicketNoteForm()
        return context
