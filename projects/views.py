from django.views.generic import ListView, DetailView, View, TemplateView
from django.views.generic.edit import UpdateView, CreateView, FormView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import models
from .models import Project, CloudSignConfig, ContractFile, Participant
from .forms import CloudSignConfigForm, ProjectForm, ContractFileFormSet, ParticipantFormSet, EmbeddedParticipantFormSet
from .cloudsign_api import CloudSignAPIClient
import re
import logging
import requests
import os
from django.conf import settings
from django.http import HttpResponse, Http404
from uuid import UUID

logger = logging.getLogger(__name__)

class HomeView(TemplateView):
    """
    Renders the home page.
    """
    template_name = 'projects/home.html'

class ProjectListView(ListView):
    """
    Displays a list of projects with pagination, search, and filtering capabilities.
    """
    model = Project
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        """
        Overrides the default queryset to implement search and date filtering.
        The search is performed across 'title' and 'description' fields.
        The date filtering is based on a 'due_date' range.
        """
        queryset = super().get_queryset().order_by('-created_at')
        search_query = self.request.GET.get('search', '')
        date_from = self.request.GET.get('date_from', '')
        date_to = self.request.GET.get('date_to', '')

        if search_query:
            queryset = queryset.filter(
                models.Q(title__icontains=search_query) |
                models.Q(description__icontains=search_query)
            )
        
        if date_from:
            queryset = queryset.filter(due_date__gte=date_from)
        
        if date_to:
            queryset = queryset.filter(due_date__lte=date_to)

        return queryset

    def get_context_data(self, **kwargs):
        """
        Adds the search and filter query parameters to the context so they can be
        displayed in the template.
        """
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        return context

class ProjectDetailView(DetailView):
    """
    Displays the details of a single project, including its CloudSign status
    and participants if a document is associated with it.
    """
    model = Project
    template_name = 'projects/project_detail.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        """
        Fetches document details from CloudSign API and adds them to the context
        for rendering in the template. The status code from the API is mapped to
        a human-readable Japanese string.
        """
        context = super().get_context_data(**kwargs)
        project = self.get_object()

        status_map = {
            0: "下書き",
            1: "先方確認中",
            2: "締結済",
            3: "取消、または却下",
            4: "テンプレート",
        }

        if project.cloudsign_document_id:
            try:
                client = CloudSignAPIClient()
                document_details = client.get_document(project.cloudsign_document_id)
                
                status_code = document_details.get('status')
                context['cloudsign_status'] = status_map.get(status_code, f"不明なステータス ({status_code})")

                context['cloudsign_participants'] = document_details.get('participants', [])
            except requests.exceptions.HTTPError as e:
                error_message = f"CloudSign APIエラー ({e.response.status_code}): {e.response.text}"
                logger.error(f"[{self.__class__.__name__}][get_document_details][Project: {project.id}] Failed to get CloudSign document details: {error_message}", exc_info=True)
                context['cloudsign_status'] = f"ステータス取得エラー: {error_message}"
                context['cloudsign_participants'] = []
            except requests.exceptions.RequestException as e:
                error_message = f"ネットワークエラー: {e}"
                logger.error(f"[{self.__class__.__name__}][get_document_details][Project: {project.id}] Network error while getting document details: {error_message}", exc_info=True)
                context['cloudsign_status'] = f"ステータス取得エラー: {error_message}"
                context['cloudsign_participants'] = []
            except Exception as e:
                error_message = f"予期せぬエラー: {e}"
                logger.error(f"[{self.__class__.__name__}][get_document_details][Project: {project.id}] Unexpected error while getting document details: {error_message}", exc_info=True)
                context['cloudsign_status'] = f"ステータス取得エラー: {error_message}"
                context['cloudsign_participants'] = []
        
        context['files'] = project.files.all()
        return context

class ProjectUpdateView(UpdateView):
    """
    Handles updating an existing project.
    It can also update the associated CloudSign document or create one if it doesn't exist.
    """
    model = Project
    template_name = 'projects/project_form.html'
    form_class = ProjectForm
    success_url = reverse_lazy('projects:project_list')

    def get_context_data(self, **kwargs):
        """
        Adds the formset for contract file uploads to the context.
        """
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['formset'] = ContractFileFormSet(self.request.POST, self.request.FILES, instance=self.object)
        else:
            data['formset'] = ContractFileFormSet(instance=self.object)
        return data

    def post(self, request, *args, **kwargs):
        """
        Handles POST request, validating both the project form and the file formset.
        """
        self.object = self.get_object()
        form = self.get_form()
        formset = ContractFileFormSet(request.POST, request.FILES, instance=self.object)

        if form.is_valid() and formset.is_valid():
            return self.form_valid(form, formset)
        else:
            return self.form_invalid(form, formset)

    def form_valid(self, form, formset):
        """
        If the form is valid, saves the project and handles CloudSign document update or creation.
        """
        self.object = form.save()
        formset.save()

        if self.object.cloudsign_document_id:
            try:
                client = CloudSignAPIClient()
                cloudsign_response = client.update_document(
                    document_id=self.object.cloudsign_document_id,
                    update_data={
                        "title": self.object.title,
                        "note": self.object.description,
                    }
                )
                messages.success(self.request, f"CloudSignドキュメント (ID: {self.object.cloudsign_document_id}) が更新されました。")
            except Exception as e:
                error_message = f"CloudSign連携エラー: {e}"
                logger.error(f"Failed to update CloudSign document {self.object.cloudsign_document_id}: {error_message}", exc_info=True)
                form.add_error(None, error_message)
                return self.form_invalid(form, formset)
        elif not self.object.cloudsign_document_id:
            all_files = [contract_file.file for contract_file in self.object.files.all()]

            if all_files:
                try:
                    client = CloudSignAPIClient()
                    cloudsign_response = client.create_document(
                        title=self.object.title
                    )
                    document_id = cloudsign_response.get('id')
                    if document_id:
                        self.object.cloudsign_document_id = document_id
                        self.object.save()
                        messages.success(self.request, f"案件が更新され、新しいCloudSignドキュメント (ID: {document_id}) が作成されました。")
                    else:
                        messages.warning(self.request, "CloudSign APIからドキュメントIDが返されませんでした。")
                except Exception as e:
                    error_message = f"CloudSign連携エラー: {e}"
                    logger.error(f"Failed to create CloudSign document during update: {error_message}", exc_info=True)
                    form.add_error(None, error_message)
                    return self.form_invalid(form, formset)
            else:
                messages.info(self.request, "ファイルがないため、CloudSignドキュメントは作成されませんでした。")

        messages.success(self.request, "案件が正常に更新されました。")
        return redirect(self.get_success_url())

    def form_invalid(self, form, formset):
        """
        If the form is invalid, re-renders the page with the form and formset errors.
        """
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

class ProjectDeleteView(DeleteView):
    """
    Handles the deletion of a project.
    """
    model = Project
    template_name = 'projects/project_confirm_delete.html'
    success_url = reverse_lazy('projects:project_list')

class CloudSignConfigView(View):
    """
    Manages the CloudSign API configuration settings.
    """
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

class CloudSignConfigDeleteView(DeleteView):
    """
    Handles the deletion of the singleton CloudSign configuration object.
    """
    model = CloudSignConfig
    template_name = 'projects/cloudsignconfig_confirm_delete.html'
    success_url = reverse_lazy('projects:cloudsign_config')

    def get_object(self, queryset=None):
        config = CloudSignConfig.objects.first()
        if not config:
            messages.info(self.request, "削除する設定がありません。")
            return None
        return config

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object is None:
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "CloudSign設定が正常に削除されました。")
        return response

class DocumentSendView(View):
    """
    Handles the action of sending a CloudSign document.
    """
    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        if not project.cloudsign_document_id:
            messages.error(request, "CloudSignドキュメントIDがないため、ドキュメントを送信できません。")
            return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))

        try:
            client = CloudSignAPIClient()
            client.send_document(document_id=project.cloudsign_document_id)
            messages.success(request, f"CloudSignドキュメント (ID: {project.cloudsign_document_id}) が正常に送信されました。")
        except Exception as e:
            error_message = f"CloudSign連携エラー: {e}"
            logger.error(f"[{self.__class__.__name__}][send_document][Project: {project.pk}] Error sending document: {error_message}", exc_info=True)
            messages.error(request, f"CloudSignドキュメントの送信に失敗しました: {e}")

        return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))

class DocumentDownloadView(View):
    """
    Handles the download of a completed CloudSign document.
    """
    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        if not project.cloudsign_document_id:
            messages.error(request, "CloudSignドキュメントIDがないため、ドキュメントをダウンロードできません。")
            return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))

        try:
            client = CloudSignAPIClient()
            file_content = client.download_document(project.cloudsign_document_id)
            response = HttpResponse(file_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="cloudsign_document_{project.cloudsign_document_id}.pdf"'
            return response
        except Exception as e:
            error_message = f"CloudSign連携エラー: {e}"
            logger.error(f"[{self.__class__.__name__}][download_document][Project: {project.pk}] Error downloading document: {error_message}", exc_info=True)
            messages.error(request, f"CloudSignドキュメントのダウンロードに失敗しました: {e}")
            return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))

class LogView(View):
    """
    Displays the content of the debug log file in a structured, user-friendly format.
    """
    template_name = 'projects/log_view.html'
    log_level_map = {'INFO': '情報', 'WARNING': '警告', 'ERROR': 'エラー', 'CRITICAL': '緊急', 'DEBUG': 'デバッグ'}
    context_pattern = re.compile(r'\[([^\]]+)\]\[([^\]]+)\]\[Project: ([^\]]+)\]')

    def get(self, request, *args, **kwargs):
        log_file_path = settings.LOG_DIR / 'debug.log'
        log_entries = []
        log_file_exists = os.path.exists(log_file_path)

        if log_file_exists:
            try:
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        parts = line.strip().split(' ', 6)
                        if len(parts) >= 7:
                            level, date, time, logger_name, module, process_id, message_part = parts
                            thread_id, message_content = message_part.split(' ', 1) if ' ' in message_part else (message_part, '')
                            
                            context_match = self.context_pattern.search(message_content)
                            operation, project_id = (context_match.group(2), context_match.group(3)) if context_match else (None, None)

                            log_entries.append({
                                'level': self.log_level_map.get(level, '不明'),
                                'datetime': f"{date} {time.split(',')[0]}",
                                'logger_name': logger_name,
                                'message': message_content,
                                'log_type': 'API' if 'cloudsign_api' in logger_name else '内部',
                                'operation': operation,
                                'project_id': project_id,
                                'project_url': reverse_lazy('projects:project_detail', kwargs={'pk': int(project_id)}) if project_id and project_id.isdigit() else None
                            })
            except Exception as e:
                logger.error(f"Error reading log file: {e}", exc_info=True)
        
        log_entries.reverse()
        return render(request, self.template_name, {'log_entries': log_entries, 'log_file_exists': log_file_exists})

class ProjectManageView(View):
    template_name = 'projects/project_manage_form.html'

    def get(self, request, pk=None):
        project = get_object_or_404(Project, pk=pk) if pk else None
        is_document_sent = False
        cloudsign_status_text = None

        if project and project.cloudsign_document_id:
            try:
                client = CloudSignAPIClient()
                document_details = client.get_document(project.cloudsign_document_id)
                status_code = document_details.get('status', 0)
                status_map = {0: "下書き", 1: "先方確認中", 2: "締結済", 3: "取消、または却下", 4: "テンプレート"}
                cloudsign_status_text = status_map.get(status_code, f"不明なステータス ({status_code})")
                if status_code > 0:
                    is_document_sent = True
            except Exception as e:
                logger.error(f"Failed to get CloudSign status for project {pk}: {e}", exc_info=True)
                messages.error(request, f"CloudSignドキュメントの状態取得に失敗しました: {e}")

        project_form = ProjectForm(instance=project)
        contract_file_formset = ContractFileFormSet(instance=project, prefix='files')
        participant_formset = ParticipantFormSet(instance=project, prefix='participants')

        context = {
            'project_form': project_form,
            'contract_file_formset': contract_file_formset,
            'participant_formset': participant_formset,
            'project': project,
            'is_document_sent': is_document_sent,
            'cloudsign_status_text': cloudsign_status_text,
            'title': f'案件編集: {project.title}' if project else '新規案件作成'
        }
        return render(request, self.template_name, context)

    def post(self, request, pk=None):
        project = get_object_or_404(Project, pk=pk) if pk else None
        
        project_form = ProjectForm(request.POST, instance=project)
        contract_file_formset = ContractFileFormSet(request.POST, request.FILES, instance=project, prefix='files')
        participant_formset = ParticipantFormSet(request.POST, instance=project, prefix='participants')

        context = {'project_form': project_form, 'contract_file_formset': contract_file_formset, 'participant_formset': participant_formset, 'project': project}

        if all([project_form.is_valid(), contract_file_formset.is_valid(), participant_formset.is_valid()]):
            project = project_form.save()
            contract_file_formset.instance = project
            contract_file_formset.save()
            participant_formset.instance = project
            participant_formset.save()

            if 'save_and_send' in request.POST:
                if not project.files.exists():
                    messages.error(request, "CloudSignに送信するには、少なくとも1つのファイルが必要です。")
                    return render(request, self.template_name, context)

                if not project.participants.exists():
                    messages.error(request, "CloudSignに送信するには、少なくとも1人の宛先が必要です。")
                    return render(request, self.template_name, context)

                try:
                    client = CloudSignAPIClient()
                    
                    if not project.cloudsign_document_id:
                        doc = client.create_document(project.title)
                        project.cloudsign_document_id = doc['id']
                        project.save()

                    # Add participants and files
                    for p in project.participants.all():
                        if not p.cloudsign_participant_id:
                            p.cloudsign_participant_id = client.add_participant(project.cloudsign_document_id, p.email, p.name)
                            p.save()
                    
                    for f in project.files.all():
                        client.add_file_to_document(project.cloudsign_document_id, f.file)

                    client.send_document(project.cloudsign_document_id)
                    messages.success(request, f"案件「{project.title}」が保存され、CloudSignで正常に送信されました。")
                except Exception as e:
                    messages.error(request, f"CloudSignへの送信中にエラーが発生しました: {e}")
                    logger.error(f"Error during CloudSign send for project {project.pk}: {e}", exc_info=True)
                    return render(request, self.template_name, context)

                return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': project.pk}))
            else:
                messages.success(request, "案件と関連データが下書きとして保存されました。")
                return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': project.pk}))
        else:
            messages.error(request, "入力内容にエラーがあります。")
            return render(request, self.template_name, context)

# --- Views for Embedded Signing Feature ---
class EmbeddedProjectCreateView(View):
    """
    Handles the creation of a new project specifically for embedded signing.
    """
    form_template_name = 'projects/embedded_project_form.html'
    success_url_name = 'projects:embedded_project_create_success'

    def get(self, request, *args, **kwargs):
        """
        Handles GET requests by displaying the forms for creating a new embedded signing project.
        """
        context = {
            'project_form': ProjectForm(),
            'contract_file_formset': ContractFileFormSet(prefix='files'),
            'participant_formset': EmbeddedParticipantFormSet(prefix='participants'),
            'title': '新規組み込み署名案件作成',
        }
        return render(request, self.form_template_name, context)

    def post(self, request, *args, **kwargs):
        """
        Handles POST requests, validating forms, calling the CloudSign API, and redirecting to a success page.
        """
        project_form = ProjectForm(request.POST)
        contract_file_formset = ContractFileFormSet(request.POST, request.FILES, prefix='files')
        participant_formset = EmbeddedParticipantFormSet(request.POST, prefix='participants')

        context = {
            'project_form': project_form,
            'contract_file_formset': contract_file_formset,
            'participant_formset': participant_formset,
            'title': '新規組み込み署名案件作成',
        }

        forms_are_valid = all([
            project_form.is_valid(),
            contract_file_formset.is_valid(),
            participant_formset.is_valid()
        ])

        if not forms_are_valid:
            messages.error(request, "入力内容にエラーがあります。")
            return render(request, self.form_template_name, context)

        files = [form.cleaned_data['file'] for form in contract_file_formset if form.cleaned_data.get('file') and not form.cleaned_data.get('DELETE')]
        if not files:
            messages.error(request, "CloudSignドキュメント作成には、少なくとも1つのファイルが必要です。")
            return render(request, self.form_template_name, context)

        participants_data = [form.cleaned_data for form in participant_formset if form.cleaned_data and not form.cleaned_data.get('DELETE')]
        if not participants_data:
            messages.error(request, "CloudSignドキュメント作成には、少なくとも1人の宛先が必要です。")
            return render(request, self.form_template_name, context)

        if not any(p.get('is_embedded_signer') for p in participants_data):
            messages.error(request, "少なくとも1人は「組み込み署名者」として指定する必要があります。")
            return render(request, self.form_template_name, context)

        project = project_form.save()
        contract_file_formset.instance = project
        contract_file_formset.save()
        participant_formset.instance = project
        # Save participants from the formset to the database before processing
        participant_instances = participant_formset.save()

        try:
            client = CloudSignAPIClient()
            document_id, signing_urls, participants_with_cs_id = client.create_embedded_signing_document(
                title=project.title,
                files=files,
                participants_data=participants_data
            )
            
            project.cloudsign_document_id = document_id
            project.save()

            # Create a mapping of email to participant instance for efficient lookup
            participant_map = {p.email: p for p in participant_instances}

            # Update participants with CloudSign IDs and signing URLs
            for p_data in participants_with_cs_id:
                participant = participant_map.get(p_data.get('email'))
                if participant:
                    participant.cloudsign_participant_id = p_data.get('cloudsign_participant_id')
                    # Find the corresponding signing URL info
                    url_info = next((url for url in signing_urls if url.get('cloudsign_participant_id') == p_data.get('cloudsign_participant_id')), None)
                    if url_info:
                        participant.signing_url = url_info.get('url')
                    participant.save()
            
            request.session['embedded_project_id'] = project.id

            messages.success(request, "案件が作成され、組み込み署名URLが生成されました。")
            return redirect(self.success_url_name)

        except Exception as e:
            logger.error(f"[{self.__class__.__name__}][post][Project: {project.id}] Error creating embedded signing document: {e}", exc_info=True)
            messages.error(request, f"CloudSign連携中にエラーが発生しました: {e}")
            project.delete() # Rollback
            return render(request, self.form_template_name, context)


class EmbeddedProjectSuccessView(TemplateView):
    """
    Displays the generated embedded signing URLs after a project is successfully created.
    """
    template_name = 'projects/embedded_project_success.html'

    def get(self, request, *args, **kwargs):
        project_id = request.session.pop('embedded_project_id', None)

        if not project_id:
            messages.warning(request, "表示する署名URL情報がありません。")
            return redirect(reverse_lazy('projects:project_list'))

        project = get_object_or_404(Project, pk=project_id)
        
        # Retrieve participants with saved URLs from the database to ensure data is fresh
        participants_with_urls = project.participants.filter(is_embedded_signer=True, signing_url__isnull=False)

        context = {
            'project': project,
            'participants_with_urls': participants_with_urls, # Pass the queryset to the template
        }
        return render(request, self.template_name, context)

class SigningView(DetailView):
    """
    Displays the signing page for a specific participant.
    """
    model = Participant
    template_name = 'projects/signing_page.html'
    context_object_name = 'participant'
    slug_field = 'id'
    slug_url_kwarg = 'signer_id'

    def get_object(self, queryset=None):
        """
        Retrieves the Participant object using a UUID from the URL.
        """
        signer_id = self.kwargs.get(self.slug_url_kwarg)
        try:
            # Ensure it's a valid UUID, though the URL pattern should handle this.
            if isinstance(signer_id, str):
                UUID(signer_id)
        except (ValueError, TypeError):
            raise Http404("無効な署名者IDです。")
        return get_object_or_404(Participant, id=signer_id)