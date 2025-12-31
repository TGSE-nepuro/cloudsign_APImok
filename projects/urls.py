from django.urls import path
from .views import (
    HomeView, # Import HomeView
    ProjectListView,
    ProjectDetailView,
    ProjectCreateView,
    ProjectUpdateView,
    ProjectDeleteView,
    CloudSignConfigView,
    ParticipantCreateView # Add this import
)

app_name = 'projects'

urlpatterns = [
    path('', HomeView.as_view(), name='home'), # Set HomeView as the root
    path('list/', ProjectListView.as_view(), name='project_list'), # Changed path for ProjectListView
    path('<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
    path('new/', ProjectCreateView.as_view(), name='project_create'),
    path('<int:pk>/edit/', ProjectUpdateView.as_view(), name='project_update'),
    path('<int:pk>/delete/', ProjectDeleteView.as_view(), name='project_delete'),
    path('cloudsign-config/', CloudSignConfigView.as_view(), name='cloudsign_config'),
    path('<int:pk>/add-participant/', ParticipantCreateView.as_view(), name='add_participant'),
]
