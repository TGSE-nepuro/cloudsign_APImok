from django.db import models

class Project(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    cloudsign_document_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title