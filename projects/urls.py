from django.urls import path
from .views import (
    HomeView, ProjectListView, ProjectDetailView, ProjectManageView,
    ProjectDeleteView, CloudSignConfigView, CloudSignConfigDeleteView,
    LogView, DocumentSendView, DocumentDownloadView, ConsentMyPageView,
    EmbeddedProjectCreateView, EmbeddedProjectSuccessView, SigningView,
)

app_name = 'projects'

urlpatterns = [
    path('', HomeView.as_view(), name='home'), # Set HomeView as the root
    path('list/', ProjectListView.as_view(), name='project_list'), # Changed path for ProjectListView
    path('<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
    path('new/', ProjectManageView.as_view(), name='project_manage_new'),
    path('<int:pk>/edit/', ProjectManageView.as_view(), name='project_manage_edit'),
    path('<int:pk>/delete/', ProjectDeleteView.as_view(), name='project_delete'),
    path('cloudsign-config/', CloudSignConfigView.as_view(), name='cloudsign_config'),
    path('cloudsign-config/delete/', CloudSignConfigDeleteView.as_view(), name='cloudsign_config_delete'),
    path('logs/', LogView.as_view(), name='log_view'), # Add this URL
    path('consent/', ConsentMyPageView.as_view(), name='consent_mypage'),
    path('<int:pk>/send-document/', DocumentSendView.as_view(), name='send_document'),
    path('<int:pk>/download-document/', DocumentDownloadView.as_view(), name='download_document'),
    path('embedded-new/', EmbeddedProjectCreateView.as_view(), name='embedded_project_create_new'),
    path('embedded-new/success/', EmbeddedProjectSuccessView.as_view(), name='embedded_project_create_success'),
    path('signing/<uuid:signer_id>/', SigningView.as_view(), name='signing_view'),
]
