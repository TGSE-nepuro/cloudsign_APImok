from django.contrib import admin
from .models import Project, CloudSignConfig # Import CloudSignConfig

admin.site.register(Project)

@admin.register(CloudSignConfig) # Register CloudSignConfig
class CloudSignConfigAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'api_base_url')

    def has_add_permission(self, request):
        # Allow adding only if no instance exists
        return not CloudSignConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion
        return False