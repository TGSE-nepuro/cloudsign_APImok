from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, TemplateView
from django.urls import reverse_lazy
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages # Import messages framework
from .models import Project, CloudSignConfig
from .forms import CloudSignConfigForm, ProjectForm # Import ProjectForm
from .cloudsign_api import CloudSignAPIClient # Import CloudSignAPIClient
import logging

logger = logging.getLogger(__name__)

class HomeView(TemplateView):
    template_name = 'projects/home.html'

class ProjectListView(ListView):
    model = Project
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'

class ProjectDetailView(DetailView):
    model = Project
    template_name = 'projects/project_detail.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        if project.cloudsign_document_id:
            try:
                client = CloudSignAPIClient()
                # Assuming get_document_status returns a dict with 'status' key
                document_status = client.get_document_status(project.cloudsign_document_id)
                context['cloudsign_status'] = document_status.get('status', '取得できませんでした')
            except Exception as e:
                logger.error(f"Failed to get CloudSign document status for project {project.id}: {e}")
                context['cloudsign_status'] = f"ステータス取得エラー: {e}"
        return context

class ProjectCreateView(CreateView):
    model = Project
    template_name = 'projects/project_form.html'
    form_class = ProjectForm # Use ProjectForm
    success_url = reverse_lazy('projects:project_list')

    def form_valid(self, form):
        project = form.save(commit=False)
        try:
            client = CloudSignAPIClient()
            # Prepare document data for CloudSign API
            document_data = {
                "title": project.title,
                "description": project.description,
                # Add other necessary fields for CloudSign document creation
                # For now, only title and description are passed to CloudSign API
            }
            cloudsign_response = client.create_document(document_data)
            # Assuming the CloudSign API returns the document ID in the response
            project.cloudsign_document_id = cloudsign_response.get('document_id')
            messages.success(self.request, "案件が正常に作成され、CloudSignドキュメントも作成されました。")
        except Exception as e:
            logger.error(f"Failed to create CloudSign document for new project: {e}")
            messages.error(self.request, f"案件は作成されましたが、CloudSignドキュメントの作成に失敗しました: {e}")
            # Decide whether to prevent project creation if CloudSign document creation fails
            # For now, we allow project creation but show an error for CloudSign part.
            project.cloudsign_document_id = None # Ensure it's not set if API call failed

        project.save()
        return super().form_valid(form)

class ProjectUpdateView(UpdateView):
    model = Project
    template_name = 'projects/project_form.html'
    form_class = ProjectForm # Use ProjectForm
    success_url = reverse_lazy('projects:project_list')

    def form_valid(self, form):
        project = form.save(commit=False)
        try:
            client = CloudSignAPIClient()
            if project.cloudsign_document_id:
                # If document already exists in CloudSign, attempt to update it
                # This assumes CloudSign API has an update endpoint and client.update_document is implemented
                # For now, we'll just log a message as update_document is a placeholder
                logger.info(f"Attempting to update CloudSign document {project.cloudsign_document_id} for project {project.id}")
                # Example: client.update_document(project.cloudsign_document_id, {"title": project.title, ...})
                messages.info(self.request, "案件は更新されましたが、CloudSignドキュメントの更新機能は未実装です。")
            else:
                # If cloudsign_document_id is empty, create a new document
                document_data = {
                    "title": project.title,
                    "description": project.description,
                }
                cloudsign_response = client.create_document(document_data)
                project.cloudsign_document_id = cloudsign_response.get('document_id')
                messages.success(self.request, "案件が更新され、新しいCloudSignドキュメントが作成されました。")
        except Exception as e:
            logger.error(f"Failed to interact with CloudSign API during project update for project {project.id}: {e}")
            messages.error(self.request, f"案件は更新されましたが、CloudSign APIとの連携に失敗しました: {e}")
            # If API call failed and it was a new creation attempt, ensure ID is not set
            if not project.cloudsign_document_id:
                project.cloudsign_document_id = None

        project.save()
        return super().form_valid(form)

class ProjectDeleteView(DeleteView):
    model = Project
    template_name = 'projects/project_confirm_delete.html'
    success_url = reverse_lazy('projects:project_list')

class CloudSignConfigView(View):
    template_name = 'projects/cloudsignconfig_form.html'

    def get(self, request, *args, **kwargs):
        config = CloudSignConfig.objects.first()
        form = CloudSignConfigForm(instance=config)
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        config = CloudSignConfig.objects.first()
        form = CloudSignConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(self.request, "CloudSign設定が正常に更新されました。")
            return redirect(reverse_lazy('projects:cloudsign_config')) # Redirect to itself after save
        messages.error(self.request, "CloudSign設定の更新に失敗しました。入力内容を確認してください。")
        return render(request, self.template_name, {'form': form})