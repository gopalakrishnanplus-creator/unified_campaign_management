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
        fields = ["free_text", "uploaded_file"]
        widgets = {
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
        self.fields["free_text"].label = "Describe the issue"
        self.fields["uploaded_file"].label = "Upload screenshot or image"

    def clean_uploaded_file(self):
        uploaded_file = self.cleaned_data.get("uploaded_file")
        if uploaded_file and uploaded_file.size > 8 * 1024 * 1024:
            raise forms.ValidationError("Please upload a file smaller than 8 MB.")
        return uploaded_file
