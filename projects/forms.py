from django import forms
from django.forms.models import BaseInlineFormSet, inlineformset_factory
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import CloudSignConfig, Project, ContractFile, Participant

class CloudSignConfigForm(forms.ModelForm):
    class Meta:
        model = CloudSignConfig
        fields = ['client_id', 'api_base_url']
        widgets = {
            'client_id': forms.TextInput(attrs={'class': 'form-control'}),
            'api_base_url': forms.URLInput(attrs={'class': 'form-control'}),
        }

class ProjectForm(forms.ModelForm):
    # Explicitly define amount as a CharField to allow comma input
    amount = forms.CharField(
        label=_("金額"),
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Project
        fields = ['title', 'description', 'customer_info', 'due_date', 'amount']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'customer_info': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def clean_amount(self):
        amount_str = self.cleaned_data.get('amount')
        if not amount_str:
            return None
        
        # Remove commas
        amount_str = str(amount_str).replace(',', '')
        
        try:
            # Convert to integer
            return int(amount_str)
        except (ValueError, TypeError):
            raise ValidationError(_("有効な数値を入力してください。"), code='invalid')

class ContractFileForm(forms.ModelForm):
    class Meta:
        model = ContractFile
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'application/pdf'}),
        }

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

ParticipantFormSet = inlineformset_factory(
    Project,
    Participant,
    fields=('name', 'email', 'order'),
    extra=1,
    can_delete=True,
    widgets={
        'name': forms.TextInput(attrs={'class': 'form-control'}),
        'email': forms.EmailInput(attrs={'class': 'form-control'}),
        'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
    }
)

# --- Forms for Embedded Signing Feature ---

class EmbeddedParticipantForm(forms.ModelForm):
    class Meta:
        model = Participant
        fields = ['name', 'email', 'order', 'tel', 'is_embedded_signer']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'tel': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('例: 09012345678')}),
            'is_embedded_signer': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_embedded = cleaned_data.get("is_embedded_signer")
        tel = cleaned_data.get("tel")

        if is_embedded and not tel:
            raise ValidationError(
                _("組み込み署名者には電話番号が必須です。"),
                code='tel_required_for_embedded_signer'
            )
        return cleaned_data

EmbeddedParticipantFormSet = inlineformset_factory(
    Project,
    Participant,
    form=EmbeddedParticipantForm,
    extra=1,
    can_delete=True
)
