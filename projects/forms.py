from django import forms
from .models import CloudSignConfig, Project # Import Project model

class CloudSignConfigForm(forms.ModelForm):
    class Meta:
        model = CloudSignConfig
        fields = ['client_id', 'api_base_url']

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['title', 'description', 'customer_info', 'due_date', 'amount']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
