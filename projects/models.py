from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class Project(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    cloudsign_document_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class CloudSignConfig(models.Model):
    client_id = models.CharField(max_length=255, unique=True, help_text=_("CloudSign API Client ID"))
    api_base_url = models.URLField(default="https://api-sandbox.cloudsign.jp", help_text=_("CloudSign API Base URL (e.g., https://api-sandbox.cloudsign.jp)"))
    
    class Meta:
        verbose_name = _("CloudSign Configuration")
        verbose_name_plural = _("CloudSign Configuration")

    def clean(self):
        # Ensure only one instance of CloudSignConfig exists
        if CloudSignConfig.objects.exists() and self.pk != CloudSignConfig.objects.get().pk:
            raise ValidationError(_('Only one CloudSign Configuration can be created.'))
        super().clean()

    def save(self, *args, **kwargs):
        self.clean() # Call clean method before saving
        super().save(*args, **kwargs)

    def __str__(self):
        return _("CloudSign Configuration")