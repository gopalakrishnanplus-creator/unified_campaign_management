from django import forms

from apps.accounts.models import User
from apps.campaigns.models import Campaign

from .models import Department, Ticket, TicketAttachment, TicketCategory, TicketNote, TicketRoutingEvent, TicketTypeDefinition


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            if not data:
                return []
            return [single_file_clean(item, initial) for item in data]
        return single_file_clean(data, initial)


class TicketCreateForm(forms.ModelForm):
    ticket_category = forms.ModelChoiceField(queryset=TicketCategory.objects.none(), empty_label="Select category")
    ticket_type_definition = forms.ModelChoiceField(
        queryset=TicketTypeDefinition.objects.none(),
        required=False,
        empty_label="Select ticket type",
    )
    new_ticket_type_name = forms.CharField(
        required=False,
        max_length=120,
        help_text="Use this when the required ticket type does not exist yet.",
    )

    class Meta:
        model = Ticket
        fields = [
            "title",
            "description",
            "ticket_category",
            "ticket_type_definition",
            "user_type",
            "source_system",
            "priority",
            "department",
            "campaign",
            "requester_name",
            "requester_email",
            "requester_company",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ticket_category"].queryset = TicketCategory.objects.filter(is_active=True).order_by("display_order", "name")
        self.fields["ticket_type_definition"].queryset = TicketTypeDefinition.objects.filter(is_active=True).select_related("category").order_by(
            "category__display_order",
            "category__name",
            "name",
        )

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("ticket_category")
        ticket_type_definition = cleaned_data.get("ticket_type_definition")
        new_ticket_type_name = (cleaned_data.get("new_ticket_type_name") or "").strip()

        if not category:
            self.add_error("ticket_category", "Please choose a ticket category.")

        if not ticket_type_definition and not new_ticket_type_name:
            self.add_error("ticket_type_definition", "Select a ticket type or create a new one.")

        if ticket_type_definition and category and ticket_type_definition.category_id != category.id:
            self.add_error("ticket_type_definition", "Selected ticket type does not belong to the chosen category.")

        cleaned_data["new_ticket_type_name"] = new_ticket_type_name
        return cleaned_data


class TicketStatusForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["status"]


class TicketDelegationForm(forms.Form):
    assignee = forms.ModelChoiceField(queryset=User.objects.none())

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        queryset = User.objects.filter(is_active=True)
        if user.department_id:
            queryset = queryset.filter(department=user.department)
        self.fields["assignee"].queryset = queryset.order_by("full_name", "email")


class TicketNoteForm(forms.ModelForm):
    attachments = MultipleFileField(
        required=False,
    )

    class Meta:
        model = TicketNote
        fields = ["body", "attachments"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}

    def clean_attachments(self):
        files = self.files.getlist("attachments")
        if len(files) > 3:
            raise forms.ValidationError("You can upload at most three files per note.")
        for file in files:
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError(f"{file.name} exceeds the 5 MB limit.")
        return files

    def save_attachments(self, note):
        for file in self.files.getlist("attachments"):
            TicketAttachment.objects.create(note=note, file=file)


class TicketFilterForm(forms.Form):
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search ticket number, title, or requester"}),
    )
    status = forms.ChoiceField(required=False, choices=[("", "All statuses"), *Ticket.Status.choices])
    priority = forms.ChoiceField(required=False, choices=[("", "All priorities"), *Ticket.Priority.choices])
    ticket_category = forms.ModelChoiceField(
        queryset=TicketCategory.objects.filter(is_active=True).order_by("display_order", "name"),
        required=False,
        empty_label="All categories",
    )
    ticket_type_definition = forms.ModelChoiceField(
        queryset=TicketTypeDefinition.objects.filter(is_active=True).select_related("category").order_by("category__name", "name"),
        required=False,
        empty_label="All ticket types",
    )
    campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.order_by("name"),
        required=False,
        empty_label="All campaigns",
    )
    period_days = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All periods"),
            ("7", "Last 7 days"),
            ("30", "Last 30 days"),
            ("90", "Last 90 days"),
        ],
    )
    sort_by = forms.ChoiceField(
        required=False,
        choices=[
            ("newest", "Newest first"),
            ("oldest", "Oldest first"),
            ("priority_desc", "Priority: highest first"),
            ("status", "Status order"),
            ("updated", "Recently updated"),
        ],
        initial="newest",
    )


class TicketDistributionFilterForm(forms.Form):
    ticket_category = forms.ModelChoiceField(
        queryset=TicketCategory.objects.filter(is_active=True).order_by("display_order", "name"),
        required=False,
        empty_label="All categories",
    )
    ticket_type_definition = forms.ModelChoiceField(
        queryset=TicketTypeDefinition.objects.filter(is_active=True).select_related("category").order_by("category__name", "name"),
        required=False,
        empty_label="All ticket types",
    )
    source_system = forms.ChoiceField(required=False, choices=[("", "All systems"), *Ticket.SourceSystem.choices])
    period_days = forms.ChoiceField(
        required=False,
        choices=[
            ("14", "Last 14 days"),
            ("30", "Last 30 days"),
            ("90", "Last 90 days"),
            ("180", "Last 180 days"),
        ],
        initial="30",
    )
