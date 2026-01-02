from django.urls import path
from .views import (
    HomeView, # Import HomeView
    ProjectListView,
    ProjectDetailView,
    ProjectManageView,
    ProjectDeleteView,
    CloudSignConfigView,
    DocumentSendView,
    DocumentDownloadView,
    LogView
)

app_name = 'projects'

urlpatterns = [
    path('', HomeView.as_view(), name='home'), # Set HomeView as the root
    path('list/', ProjectListView.as_view(), name='project_list'), # Changed path for ProjectListView
    path('<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
    path('new/', ProjectManageView.as_view(), name='project_create'),
    path('<int:pk>/edit/', ProjectManageView.as_view(), name='project_update'),
    path('<int:pk>/delete/', ProjectDeleteView.as_view(), name='project_delete'),
    path('cloudsign-config/', CloudSignConfigView.as_view(), name='cloudsign_config'),
    path('logs/', LogView.as_view(), name='log_view'), # Add this URL
    path('<int:pk>/send-document/', DocumentSendView.as_view(), name='send_document'),
    path('<int:pk>/download-document/', DocumentDownloadView.as_view(), name='download_document'),
]
