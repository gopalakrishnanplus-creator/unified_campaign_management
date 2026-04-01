from django import forms

from apps.accounts.models import User

from .models import Department, Ticket, TicketAttachment, TicketNote, TicketRoutingEvent


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
    class Meta:
        model = Ticket
        fields = [
            "title",
            "description",
            "ticket_type",
            "user_type",
            "source_system",
            "priority",
            "department",
            "campaign",
            "requester_name",
            "requester_email",
            "requester_company",
        ]


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
    status = forms.ChoiceField(required=False, choices=[("", "All statuses"), *Ticket.Status.choices])
    campaign = forms.IntegerField(required=False)
    period_days = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All periods"),
            ("7", "Last 7 days"),
            ("30", "Last 30 days"),
            ("90", "Last 90 days"),
        ],
    )
