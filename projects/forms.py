from django import forms
from .models import CloudSignConfig

class CloudSignConfigForm(forms.ModelForm):
    class Meta:
        model = CloudSignConfig
        fields = ['client_id', 'api_base_url']
