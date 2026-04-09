from django import forms

from apps.campaigns.models import Campaign

from .models import SupportRequest


class SupportRequestForm(forms.ModelForm):
    campaign = forms.ModelChoiceField(queryset=Campaign.objects.all(), required=False)

    class Meta:
        model = SupportRequest
        fields = ["requester_name", "requester_email", "requester_company", "campaign", "subject", "free_text"]
        widgets = {"free_text": forms.Textarea(attrs={"rows": 4})}


class SupportOtherIssueForm(forms.ModelForm):
    class Meta:
        model = SupportRequest
        fields = ["requester_name", "requester_number", "requester_email", "free_text", "uploaded_file"]
        widgets = {
            "requester_name": forms.TextInput(
                attrs={
                    "placeholder": "Enter your name",
                }
            ),
            "requester_number": forms.TextInput(
                attrs={
                    "placeholder": "Enter your phone number",
                    "inputmode": "tel",
                }
            ),
            "requester_email": forms.EmailInput(
                attrs={
                    "placeholder": "Enter your email address",
                }
            ),
            "free_text": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Describe what happened and what the user was trying to do.",
                }
            ),
            "uploaded_file": forms.ClearableFileInput(
                attrs={
                    "accept": ".jpg,.jpeg,.png,.heic,.svg,.webp",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requester_name"].label = "Name"
        self.fields["requester_number"].label = "Phone Number"
        self.fields["requester_email"].label = "Email Address"
        self.fields["free_text"].label = "Describe the issue"
        self.fields["uploaded_file"].label = "Upload screenshot or image"

    def clean_requester_number(self):
        requester_number = (self.cleaned_data.get("requester_number") or "").strip()
        if not requester_number:
            raise forms.ValidationError("Please enter a phone number.")
        return requester_number

    def clean_uploaded_file(self):
        uploaded_file = self.cleaned_data.get("uploaded_file")
        if uploaded_file and uploaded_file.size > 8 * 1024 * 1024:
            raise forms.ValidationError("Please upload a file smaller than 8 MB.")
        return uploaded_file
