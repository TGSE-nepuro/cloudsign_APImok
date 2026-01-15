from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import FileExtensionValidator

def validate_file_size(value):
    """
    Custom validator to ensure that the uploaded file size does not exceed 20 MB.
    This limit is imposed to manage storage and network bandwidth, and
    potentially align with CloudSign API limits.
    """
    limit = 20 * 1024 * 1024  # 20 MB
    if value.size > limit:
        raise ValidationError(_('File size cannot exceed 20 MB.'))

class Project(models.Model):
    """
    Represents a project in the application. Each project can be associated
    with a CloudSign document.
    """
    title = models.CharField(max_length=200, verbose_name=_("案件名"))
    description = models.TextField(blank=True, null=True, verbose_name=_("案件概要"))
    customer_info = models.TextField(blank=True, null=True, help_text=_("取引先情報"), verbose_name=_("取引先情報"))
    due_date = models.DateField(blank=True, null=True, help_text=_("期日"), verbose_name=_("期日"))
    amount = models.BigIntegerField(blank=True, null=True, help_text=_("金額"), verbose_name=_("金額"))
    # Stores the ID of the corresponding document in CloudSign, if created.
    cloudsign_document_id = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("CloudSign Document ID"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("作成日時"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新日時"))

    class Meta:
        verbose_name = _("案件")
        verbose_name_plural = _("案件")
        ordering = ['-created_at'] # Default ordering for project listings

    def __str__(self):
        return self.title

class ContractFile(models.Model):
    """
    Represents a file attached to a project, typically intended for CloudSign.
    """
    project = models.ForeignKey(Project, related_name='files', on_delete=models.CASCADE, verbose_name=_("案件"))
    file = models.FileField(
        upload_to='contracts/%Y/%m/%d/', # Files are organized by upload date
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']), # Only PDF files are allowed
            validate_file_size # Custom validator for file size
        ],
        verbose_name=_("契約書ファイル")
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("アップロード日時"))

    class Meta:
        verbose_name = _("契約書ファイル")
        verbose_name_plural = _("契約書ファイル")

    def __str__(self):
        return f"{self.project.title} - {self.file.name}"

class CloudSignConfig(models.Model):
    """
    Stores the configuration settings required to connect to the CloudSign API.
    Designed as a singleton model to ensure only one configuration exists.
    """
    client_id = models.CharField(max_length=255, unique=True, help_text=_("CloudSign API Client ID"), verbose_name=_("クライアントID"))
    api_base_url = models.URLField(default="https://api-sandbox.cloudsign.jp", help_text=_("CloudSign API Base URL (e.g., https://api-sandbox.cloudsign.jp)"), verbose_name=_("APIベースURL"))
    
    class Meta:
        verbose_name = _("CloudSign 設定")
        verbose_name_plural = _("CloudSign 設定")

    def clean(self):
        """
        Custom clean method to enforce the singleton pattern.
        Raises ValidationError if an attempt is made to create a second instance.
        """
        # Ensure only one instance of CloudSignConfig exists
        if CloudSignConfig.objects.exists() and self.pk != CloudSignConfig.objects.get().pk:
            raise ValidationError(_('Only one CloudSign Configuration can be created.'))
        super().clean()

    def save(self, *args, **kwargs):
        """
        Overrides save method to call clean method before saving,
        ensuring singleton constraint is always checked.
        """
        self.clean() # Call clean method before saving
        super().save(*args, **kwargs)

    def __str__(self):
        return _("CloudSign Configuration")

class Participant(models.Model):
    """
    Represents a participant (recipient) for a CloudSign document,
    linked to a local Project. This allows saving draft participants
    before sending a document.
    """
    project = models.ForeignKey(Project, related_name='participants', on_delete=models.CASCADE, verbose_name=_("案件"))
    name = models.CharField(max_length=100, verbose_name=_("宛先名"))
    email = models.EmailField(verbose_name=_("メールアドレス"))
    order = models.PositiveIntegerField(default=1, verbose_name=_("順序"))
    # New fields for CloudSign integration
    cloudsign_participant_id = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("CloudSign Participant ID"))
    # recipient_id is required for embedded signing (simple authentication)
    recipient_id = models.CharField(max_length=64, blank=True, null=True, verbose_name=_("CloudSign Recipient ID for Embedded Signing"))
    tel = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("電話番号"))
    is_embedded_signer = models.BooleanField(default=False, verbose_name=_("組み込み署名者"))

    class Meta:
        verbose_name = _("宛先")
        verbose_name_plural = _("宛先")
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} ({self.email}) for Project: {self.project.title}"