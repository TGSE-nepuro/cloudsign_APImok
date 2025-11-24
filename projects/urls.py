from django.urls import path
from .views import (
    ProjectListView,
    ProjectDetailView,
    ProjectCreateView,
    ProjectUpdateView,
    ProjectDeleteView,
    CloudSignConfigView # Import CloudSignConfigView
)

app_name = 'projects'

urlpatterns = [
    path('', ProjectListView.as_view(), name='project_list'),
    path('<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
    path('new/', ProjectCreateView.as_view(), name='project_create'),
    path('<int:pk>/edit/', ProjectUpdateView.as_view(), name='project_update'),
    path('<int:pk>/delete/', ProjectDeleteView.as_view(), name='project_delete'),
    path('cloudsign-config/', CloudSignConfigView.as_view(), name='cloudsign_config'), # Add URL for CloudSignConfig
]
