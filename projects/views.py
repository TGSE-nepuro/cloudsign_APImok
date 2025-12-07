from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, TemplateView
from django.urls import reverse_lazy
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Project, CloudSignConfig, ContractFile
from .forms import CloudSignConfigForm, ProjectForm, ContractFileFormSet
from .cloudsign_api import CloudSignAPIClient
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
                document_status = client.get_document_status(project.cloudsign_document_id)
                context['cloudsign_status'] = document_status.get('status', '取得できませんでした')
            except Exception as e:
                logger.error(f"Failed to get CloudSign document status for project {project.id}: {e}")
                context['cloudsign_status'] = f"ステータス取得エラー: {e}"
        
        context['files'] = project.files.all()
        return context

class ProjectCreateView(CreateView):
    model = Project
    template_name = 'projects/project_form.html'
    form_class = ProjectForm
    success_url = reverse_lazy('projects:project_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['formset'] = ContractFileFormSet(self.request.POST, self.request.FILES)
        else:
            data['formset'] = ContractFileFormSet()
        return data

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        formset = ContractFileFormSet(request.POST, request.FILES)

        if form.is_valid() and formset.is_valid():
            return self.form_valid(form, formset)
        else:
            return self.form_invalid(form, formset)

    def form_valid(self, form, formset):
        self.object = form.save(commit=False)

        files_to_upload = []
        for f_form in formset:
            if f_form.cleaned_data and not f_form.cleaned_data.get('DELETE', False):
                if 'file' in f_form.cleaned_data and f_form.cleaned_data['file']:
                    files_to_upload.append(f_form.cleaned_data['file'])
        
        if files_to_upload:
            try:
                client = CloudSignAPIClient()
                cloudsign_response = client.create_document(
                    title=self.object.title,
                    files=files_to_upload
                )
                document_id = cloudsign_response.get('id')
                if document_id:
                    self.object.cloudsign_document_id = document_id
                    messages.success(self.request, f"CloudSignドキュメント (ID: {document_id}) が作成されました。")
                else:
                    messages.warning(self.request, "CloudSign APIからドキュメントIDが返されませんでした。")
            except Exception as e:
                logger.error(f"Failed to create CloudSign document: {e}")
                form.add_error(None, f"CloudSign連携エラー: {e}")
                return self.form_invalid(form, formset)
        else:
            messages.info(self.request, "ファイルが添付されていないため、CloudSignドキュメントは作成されませんでした。")

        self.object.save()
        formset.instance = self.object
        formset.save()

        messages.success(self.request, "案件が正常に作成されました。")
        return redirect(self.get_success_url())

    def form_invalid(self, form, formset):
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

class ProjectUpdateView(UpdateView):
    model = Project
    template_name = 'projects/project_form.html'
    form_class = ProjectForm
    success_url = reverse_lazy('projects:project_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['formset'] = ContractFileFormSet(self.request.POST, self.request.FILES, instance=self.object)
        else:
            data['formset'] = ContractFileFormSet(instance=self.object)
        return data

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = ContractFileFormSet(request.POST, request.FILES, instance=self.object)

        if form.is_valid() and formset.is_valid():
            return self.form_valid(form, formset)
        else:
            return self.form_invalid(form, formset)

    def form_valid(self, form, formset):
        self.object = form.save()
        formset.save()

        if not self.object.cloudsign_document_id:
            all_files = [contract_file.file for contract_file in self.object.files.all()]
            
            if all_files:
                try:
                    client = CloudSignAPIClient()
                    cloudsign_response = client.create_document(
                        title=self.object.title,
                        files=all_files
                    )
                    document_id = cloudsign_response.get('id')
                    if document_id:
                        self.object.cloudsign_document_id = document_id
                        self.object.save()
                        messages.success(self.request, f"案件が更新され、新しいCloudSignドキュメント (ID: {document_id}) が作成されました。")
                    else:
                        messages.warning(self.request, "CloudSign APIからドキュメントIDが返されませんでした。")
                except Exception as e:
                    logger.error(f"Failed to create CloudSign document during update: {e}")
                    form.add_error(None, f"CloudSign連携エラー: {e}")
                    return self.form_invalid(form, formset)
            else:
                messages.info(self.request, "ファイルがないため、CloudSignドキュメントは作成されませんでした。")
        else:
            messages.info(self.request, "案件は更新されました。CloudSignドキュメントの更新機能は未実装です。")

        return redirect(self.get_success_url())

    def form_invalid(self, form, formset):
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

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
            return redirect(reverse_lazy('projects:cloudsign_config'))
        messages.error(self.request, "CloudSign設定の更新に失敗しました。入力内容を確認してください。")
        return render(request, self.template_name, {'form': form})
