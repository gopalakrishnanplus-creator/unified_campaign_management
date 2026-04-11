from django import forms

from apps.accounts.models import User

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
            "status",
            "department",
            "requester_name",
            "requester_email",
            "requester_number",
            "requester_company",
        ]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        departments = kwargs.pop("departments", None)
        super().__init__(*args, **kwargs)
        self.fields["ticket_category"].queryset = TicketCategory.objects.filter(is_active=True).order_by("display_order", "name")
        self.fields["ticket_type_definition"].queryset = TicketTypeDefinition.objects.filter(is_active=True).select_related("category").order_by(
            "category__display_order",
            "category__name",
            "name",
        )
        if departments is not None:
            self.fields["department"].queryset = departments
        else:
            self.fields["department"].queryset = Department.objects.filter(is_active=True).order_by("name")
        self.fields["department"].label_from_instance = self._department_label
        self.fields["status"].required = False
        self.fields["source_system"].initial = Ticket.SourceSystem.PROJECT_MANAGER
        self.fields["user_type"].initial = Ticket.UserType.INTERNAL
        self.fields["priority"].initial = Ticket.Priority.MEDIUM
        self.fields["status"].initial = Ticket.Status.NOT_STARTED
        if user and not self.is_bound:
            self.fields["requester_name"].initial = user.full_name
            self.fields["requester_email"].initial = user.email
            self.fields["requester_number"].initial = user.phone_number
            self.fields["requester_company"].initial = user.company

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

        if not (cleaned_data.get("requester_number") or "").strip():
            self.add_error("requester_number", "Requester number is required for internal ticket sync.")

        cleaned_data["new_ticket_type_name"] = new_ticket_type_name
        return cleaned_data

    @staticmethod
    def _department_label(department):
        manager = ""
        if department.default_recipient_id:
            manager = department.default_recipient.full_name or department.default_recipient.email
        elif department.external_manager_email:
            manager = department.external_manager_email
        label = department.display_name
        if manager:
            label = f"{label} - Auto route to {manager}"
        return label


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
        created_attachments = []
        for file in self.files.getlist("attachments"):
            created_attachments.append(TicketAttachment.objects.create(note=note, file=file))
        return created_attachments


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
