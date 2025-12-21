from django import forms
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from .models import CloudSignConfig, Project, ContractFile

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

class ContractFileForm(forms.ModelForm):
    class Meta:
        model = ContractFile
        fields = ['file']

class BaseContractFileFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        
        total_files = 0
        total_size = 0
        
        # API limits
        MAX_FILES = 100
        MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50 MB

        # Count existing files if this is an update
        if self.instance and self.instance.pk:
            existing_files = self.instance.files.all()
            total_files += existing_files.count()
            total_size += sum(f.file.size for f in existing_files)

        for form in self.forms:
            if not form.is_valid():
                continue
            
            # Skip empty forms and forms marked for deletion
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                total_files += 1
                if 'file' in form.cleaned_data and hasattr(form.cleaned_data['file'], 'size'):
                    total_size += form.cleaned_data['file'].size

        if total_files > MAX_FILES:
            raise ValidationError(f'You cannot upload more than {MAX_FILES} files in total.')

        if total_size > MAX_TOTAL_SIZE:
            raise ValidationError(f'The total file size cannot exceed 50 MB.')

# This will be used in the view to create the formset
ContractFileFormSet = forms.inlineformset_factory(
    Project,
    ContractFile,
    form=ContractFileForm,
    formset=BaseContractFileFormSet,
    extra=1,  # Show 1 extra empty form by default
    can_delete=True
)
