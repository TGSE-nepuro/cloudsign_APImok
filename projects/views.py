from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, TemplateView, FormView
from django.urls import reverse_lazy
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Project, CloudSignConfig, ContractFile
from .forms import CloudSignConfigForm, ProjectForm, ContractFileFormSet, ParticipantForm
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
                document_details = client.get_document(project.cloudsign_document_id)
                context['cloudsign_status'] = document_details.get('status', '取得できませんでした')
                context['cloudsign_participants'] = document_details.get('participants', [])
            except Exception as e:
                logger.error(f"Failed to get CloudSign document status for project {project.id}: {e}")
                context['cloudsign_status'] = f"ステータス取得エラー: {e}"
                context['cloudsign_participants'] = [] # Ensure it's always a list even on error
        
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

        # If CloudSign document exists, attempt to update it
        if self.object.cloudsign_document_id:
            try:
                client = CloudSignAPIClient()
                # Assuming CloudSign document update can take title and description
                cloudsign_response = client.update_document(
                    document_id=self.object.cloudsign_document_id,
                    update_data={
                        "title": self.object.title,
                        # Add other fields if CloudSign API supports them for document update directly
                        # For example, if description maps to a 'note' field in CloudSign
                        "note": self.object.description, 
                    }
                )
                messages.success(self.request, f"CloudSignドキュメント (ID: {self.object.cloudsign_document_id}) が更新されました。")
            except Exception as e:
                logger.error(f"Failed to update CloudSign document {self.object.cloudsign_document_id}: {e}")
                form.add_error(None, f"CloudSignドキュメント更新エラー: {e}")
                return self.form_invalid(form, formset)
        # If no CloudSign document exists, check if files are attached to create one
        elif not self.object.cloudsign_document_id: # Moved this block here and kept the files logic
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

        messages.success(self.request, "案件が正常に更新されました。")
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

class ParticipantCreateView(FormView):
    template_name = 'projects/participant_form.html'
    form_class = ParticipantForm

    def get_success_url(self):
        return reverse_lazy('projects:project_detail', kwargs={'pk': self.kwargs['pk']})

    def form_valid(self, form):
        project = get_object_or_404(Project, pk=self.kwargs['pk'])
        if not project.cloudsign_document_id:
            messages.error(self.request, "CloudSignドキュメントIDがないため、参加者を追加できません。")
            return redirect(self.get_success_url())

        try:
            client = CloudSignAPIClient()
            client.add_participant(
                document_id=project.cloudsign_document_id,
                email=form.cleaned_data['email'],
                name=form.cleaned_data['name']
            )
            messages.success(self.request, f"参加者 {form.cleaned_data['name']} が正常に追加されました。")
        except Exception as e:
            logger.error(f"Failed to add participant to CloudSign document {project.cloudsign_document_id}: {e}")
            messages.error(self.request, f"参加者の追加に失敗しました: {e}")
            return self.form_invalid(form) # Render form with errors

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = get_object_or_404(Project, pk=self.kwargs['pk'])
        context['project'] = project
        return context

class DocumentSendView(View):
    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        if not project.cloudsign_document_id:
            messages.error(request, "CloudSignドキュメントIDがないため、ドキュメントを送信できません。")
            return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))

        try:
            client = CloudSignAPIClient()
            # Assuming send_data can be an empty dict for a simple send action
            client.send_document(
                document_id=project.cloudsign_document_id,
                send_data={} 
            )
            messages.success(request, f"CloudSignドキュメント (ID: {project.cloudsign_document_id}) が正常に送信されました。")
        except Exception as e:
            logger.error(f"Failed to send CloudSign document {project.cloudsign_document_id}: {e}")
            messages.error(request, f"CloudSignドキュメントの送信に失敗しました: {e}")
        
        return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))

