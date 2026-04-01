from django import forms

from apps.campaigns.models import Campaign

from .models import SupportRequest


class SupportRequestForm(forms.ModelForm):
    campaign = forms.ModelChoiceField(queryset=Campaign.objects.all(), required=False)

    class Meta:
        model = SupportRequest
        fields = ["requester_name", "requester_email", "requester_company", "campaign", "subject", "free_text"]
        widgets = {"free_text": forms.Textarea(attrs={"rows": 4})}
