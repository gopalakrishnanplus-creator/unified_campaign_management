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
        fields = [
            "requester_name",
            "requester_number",
            "requester_email",
            "device_type",
            "device",
            "free_text",
            "uploaded_file",
        ]
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
            "device_type": forms.Select(),
            "device": forms.Select(),
            "free_text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Describe what happened, what I was trying to do, and what I saw.",
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
        self.fields["device_type"].label = "Device Type"
        self.fields["device"].label = "Device"
        self.fields["free_text"].label = "Describe the issue"
        self.fields["uploaded_file"].label = "Upload screenshot or image"
        self.fields["device_type"].required = False
        self.fields["device"].required = False
        self.fields["device_type"].choices = [("", "Select device type"), *SupportRequest.DeviceType.choices]
        self.fields["device"].choices = [("", "Select device"), *SupportRequest.Device.choices]

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


class WhatsAppChannelQueryForm(forms.ModelForm):
    class Meta:
        model = SupportRequest
        fields = [
            "doctor_id",
            "requester_name",
            "requester_number",
            "requester_email",
            "requester_company",
            "subject",
            "free_text",
            "uploaded_file",
        ]
        widgets = {
            "doctor_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "Doctor ID"}),
            "requester_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Doctor name"}),
            "requester_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "WhatsApp mobile number", "inputmode": "tel"}
            ),
            "requester_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email address"}),
            "requester_company": forms.TextInput(attrs={"class": "form-control", "placeholder": "Clinic or hospital name"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "Short query summary"}),
            "free_text": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Write the message or question for moderator review.",
                }
            ),
            "uploaded_file": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ".jpg,.jpeg,.png,.heic,.svg,.webp",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["doctor_id"].label = "Doctor ID"
        self.fields["requester_name"].label = "Doctor Name"
        self.fields["requester_number"].label = "WhatsApp Number"
        self.fields["requester_email"].label = "Email Address"
        self.fields["requester_company"].label = "Clinic / Hospital"
        self.fields["subject"].label = "Query Summary"
        self.fields["free_text"].label = "Message / Question"
        self.fields["uploaded_file"].label = "Upload image"
        for field_name in [
            "doctor_id",
            "requester_name",
            "requester_number",
            "requester_email",
            "requester_company",
            "subject",
            "free_text",
        ]:
            self.fields[field_name].required = True

    def clean_doctor_id(self):
        doctor_id = (self.cleaned_data.get("doctor_id") or "").strip()
        if not doctor_id:
            raise forms.ValidationError("Please enter the Doctor ID.")
        return doctor_id

    def clean_requester_number(self):
        requester_number = (self.cleaned_data.get("requester_number") or "").strip()
        if not requester_number:
            raise forms.ValidationError("Please enter the WhatsApp number.")
        return requester_number

    def clean_free_text(self):
        free_text = (self.cleaned_data.get("free_text") or "").strip()
        if not free_text:
            raise forms.ValidationError("Please enter the message or question.")
        return free_text

    def clean_uploaded_file(self):
        uploaded_file = self.cleaned_data.get("uploaded_file")
        if uploaded_file and uploaded_file.size > 8 * 1024 * 1024:
            raise forms.ValidationError("Please upload a file smaller than 8 MB.")
        return uploaded_file
