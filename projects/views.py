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
                logger.error(f"Failed to get CloudSign document details for project {project.id}: {error_message}")
                context['cloudsign_status'] = f"ステータス取得エラー: {error_message}"
                context['cloudsign_participants'] = []
            except requests.exceptions.RequestException as e:
                error_message = f"ネットワークエラー: {e}"
                logger.error(f"Failed to get CloudSign document details for project {project.id}: {error_message}")
                context['cloudsign_status'] = f"ステータス取得エラー: {error_message}"
                context['cloudsign_participants'] = []
            except Exception as e:
                error_message = f"予期せぬエラー: {e}"
                logger.error(f"Failed to get CloudSign document details for project {project.id}: {error_message}")
                context['cloudsign_status'] = f"ステータス取得エラー: {error_message}"
                context['cloudsign_participants'] = []
        
        context['files'] = project.files.all()
        return context

# class ProjectCreateView(CreateView):
#     """
#     Handles the creation of a new project.
#     If files are provided, it also creates a corresponding document in CloudSign.
#     """
#     model = Project
#     template_name = 'projects/project_form.html'
#     form_class = ProjectForm
#     success_url = reverse_lazy('projects:project_list')

#     def get_context_data(self, **kwargs):
#         """
#         Adds the formset for contract file uploads to the context.
#         """
#         data = super().get_context_data(**kwargs)
#         if self.request.POST:
#             data['formset'] = ContractFileFormSet(self.request.POST, self.request.FILES)
#         else:
#             data['formset'] = ContractFileFormSet()
#         return data

#     def post(self, request, *args, **kwargs):
#         """
#         Handles POST request, validating both the project form and the file formset.
#         """
#         self.object = None
#         form = self.get_form()
#         formset = ContractFileFormSet(request.POST, request.FILES)

#         if form.is_valid() and formset.is_valid():
#             return self.form_valid(form, formset)
#         else:
#             return self.form_invalid(form, formset)

#     def form_valid(self, form, formset):
#         """
#         If the form is valid, saves the project and handles CloudSign document creation.
#         """
#         self.object = form.save(commit=False)

#         files_to_upload = []
#         for f_form in formset:
#             if f_form.cleaned_data and not f_form.cleaned_data.get('DELETE', False):
#                 if 'file' in f_form.cleaned_data and f_form.cleaned_data['file']:
#                     files_to_upload.append(f_form.cleaned_data['file'])
        
#         if files_to_upload:
#             try:
#                 client = CloudSignAPIClient()
#                 cloudsign_response = client.create_document(
#                     title=self.object.title,
#                     files=files_to_upload
#                 )
#                 document_id = cloudsign_response.get('id')
#                 if document_id:
#                     self.object.cloudsign_document_id = document_id
#                     messages.success(self.request, f"CloudSignドキュメント (ID: {document_id}) が作成されました。")
#                 else:
#                     messages.warning(self.request, "CloudSign APIからドキュメントIDが返されませんでした。")
#             except requests.exceptions.HTTPError as e:
#                 error_message = f"CloudSign APIエラー ({e.response.status_code}): {e.response.text}"
#                 logger.error(f"Failed to create CloudSign document: {error_message}")
#                 form.add_error(None, f"CloudSign連携エラー: {error_message}")
#                 return self.form_invalid(form, formset)
#             except requests.exceptions.RequestException as e:
#                 error_message = f"ネットワークエラー: {e}"
#                 logger.error(f"Failed to create CloudSign document: {error_message}")
#                 form.add_error(None, f"CloudSign連携エラー: {error_message}")
#                 return self.form_invalid(form, formset)
#             except Exception as e:
#                 error_message = f"予期せぬエラー: {e}"
#                 logger.error(f"Failed to create CloudSign document: {error_message}")
#                 form.add_error(None, f"CloudSign連携エラー: {error_message}")
#                 return self.form_invalid(form, formset)
#         else:
#             messages.info(self.request, "ファイルが添付されていないため、CloudSignドキュメントは作成されませんでした。")

#         self.object.save()
#         formset.instance = self.object
#         formset.save()

#         messages.success(self.request, "案件が正常に作成されました。")
#         return redirect(self.get_success_url())

#     def form_invalid(self, form, formset):
#         """
#         If the form is invalid, re-renders the page with the form and formset errors.
#         """
#         return self.render_to_response(
#             self.get_context_data(form=form, formset=formset)
#         )

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
            except requests.exceptions.HTTPError as e:
                error_message = f"CloudSign APIエラー ({e.response.status_code}): {e.response.text}"
                logger.error(f"Failed to update CloudSign document {self.object.cloudsign_document_id}: {error_message}")
                form.add_error(None, f"CloudSignドキュメント更新エラー: {error_message}")
                return self.form_invalid(form, formset)
            except requests.exceptions.RequestException as e:
                error_message = f"ネットワークエラー: {e}"
                logger.error(f"Failed to update CloudSign document {self.object.cloudsign_document_id}: {error_message}")
                form.add_error(None, f"CloudSignドキュメント更新エラー: {error_message}")
                return self.form_invalid(form, formset)
            except Exception as e:
                error_message = f"予期せぬエラー: {e}"
                logger.error(f"Failed to update CloudSign document {self.object.cloudsign_document_id}: {error_message}")
                form.add_error(None, f"CloudSignドキュメント更新エラー: {error_message}")
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
                except requests.exceptions.HTTPError as e:
                    error_message = f"CloudSign APIエラー ({e.response.status_code}): {e.response.text}"
                    logger.error(f"Failed to create CloudSign document during update: {error_message}")
                    form.add_error(None, f"CloudSign連携エラー: {error_message}")
                    return self.form_invalid(form, formset)
                except requests.exceptions.RequestException as e:
                    error_message = f"ネットワークエラー: {e}"
                    logger.error(f"Failed to create CloudSign document during update: {error_message}")
                    form.add_error(None, f"CloudSign連携エラー: {error_message}")
                    return self.form_invalid(form, formset)
                except Exception as e:
                    error_message = f"予期せぬエラー: {e}"
                    logger.error(f"Failed to create CloudSign document during update: {error_message}")
                    form.add_error(None, f"CloudSign連携エラー: {error_message}")
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
        """
        Override get_object to fetch the single config object.
        If it doesn't exist, redirect to the config page.
        """
        config = CloudSignConfig.objects.first()
        if not config:
            messages.info(self.request, "削除する設定がありません。")
            return None # Will result in a 404, which is handled by the dispatch
        return config

    def dispatch(self, request, *args, **kwargs):
        """
        Override dispatch to handle the case where get_object returns None.
        """
        self.object = self.get_object()
        if self.object is None:
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """
        Adds a success message before deleting the object.
        """
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
            # 既に送信済みの場合は再送を防止
            detail = client.get_document(project.cloudsign_document_id)
            status = detail.get('status')
            if status is not None and status != 0:
                messages.error(request, "既に送信済みの書類です。組込み署名（SMS認証）はリマインド不可のため再送できません。")
                return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))
            # The API might require a list of participants to send, but for now we assume
            # it sends to all existing participants.
            client.send_document(document_id=project.cloudsign_document_id)
            messages.success(request, f"CloudSignドキュメント (ID: {project.cloudsign_document_id}) が正常に送信されました。")
        except requests.exceptions.HTTPError as e:
            error_message = f"CloudSign APIエラー ({e.response.status_code}): {e.response.text}"
            logger.error(f"Failed to send CloudSign document {project.cloudsign_document_id}: {error_message}")
            messages.error(request, f"CloudSignドキュメントの送信に失敗しました: {error_message}")
        except requests.exceptions.RequestException as e:
            error_message = f"ネットワークエラー: {e}"
            logger.error(f"Failed to send CloudSign document {project.cloudsign_document_id}: {error_message}")
            messages.error(request, f"CloudSignドキュメントの送信に失敗しました: {error_message}")
        except Exception as e:
            error_message = f"予期せぬエラー: {e}"
            logger.error(f"Failed to send CloudSign document {project.cloudsign_document_id}: {error_message}")
            messages.error(request, f"CloudSignドキュメントの送信に失敗しました: {error_message}")

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
            file_content, file_name = client.download_document(project.cloudsign_document_id)

            # Assuming the file is a PDF for now. A more robust implementation might
            # check the Content-Type header from the API response.
            response = HttpResponse(file_content, content_type='application/pdf')
            if file_name:
                response['Content-Disposition'] = f'attachment; filename=\"{file_name}\"'
            else:
                response['Content-Disposition'] = f'attachment; filename=\"cloudsign_document_{project.cloudsign_document_id}.pdf\"'
            return response
        except requests.exceptions.HTTPError as e:
            error_message = f"CloudSign APIエラー ({e.response.status_code}): {e.response.text}"
            logger.error(f"Failed to download CloudSign document {project.cloudsign_document_id}: {error_message}")
            messages.error(request, f"CloudSignドキュメントのダウンロードに失敗しました: {error_message}")
            return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))
        except requests.exceptions.RequestException as e:
            error_message = f"ネットワークエラー: {e}"
            logger.error(f"Failed to download CloudSign document {project.cloudsign_document_id}: {error_message}")
            messages.error(request, f"CloudSignドキュメントのダウンロードに失敗しました: {error_message}")
            return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))
        except Exception as e:
            error_message = f"予期せぬエラー: {e}"
            logger.error(f"Failed to download CloudSign document {project.cloudsign_document_id}: {error_message}")
            messages.error(request, f"CloudSignドキュメントのダウンロードに失敗しました: {error_message}")
            return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': pk}))

class LogView(View):
    """
    Displays the content of the debug log file in a structured, user-friendly format.
    """
    template_name = 'projects/log_view.html'
    log_level_map = {
        'INFO': '情報',
        'WARNING': '警告',
        'ERROR': 'エラー',
        'CRITICAL': '緊急',
        'DEBUG': 'デバッグ',
    }
    
    # Reverse map for filtering
    reverse_log_level_map = {v: k for k, v in log_level_map.items()}

    def get(self, request, *args, **kwargs):
        log_file_path = settings.LOG_DIR / 'debug.log'
        all_log_entries = []
        log_file_exists = os.path.exists(log_file_path) # Define here unconditionally

        if log_file_exists: # Now use the variable
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                log_pattern = re.compile(r'^(?P<level>[A-Z]+)\s(?P<datetime>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2},\d{3})\s(?P<module>[\w.]+)(?:\s(?P<pid>\d+))?(?:\s(?P<tid>\d+))?\s(?P<message>.*)$')
                
                buffer = []
                for line in f:
                    if log_pattern.match(line) and buffer:
                        self._process_log_buffer(buffer, all_log_entries, log_pattern)
                        buffer = []
                    buffer.append(line)
                if buffer:
                    self._process_log_buffer(buffer, all_log_entries, log_pattern)

        # Apply filters
        filtered_log_entries = all_log_entries
        
        level_filter_jp = request.GET.get('level')
        search_query = request.GET.get('search', '').lower()

        if level_filter_jp:
            level_filter_en = self.reverse_log_level_map.get(level_filter_jp, level_filter_jp)
            filtered_log_entries = [
                entry for entry in filtered_log_entries 
                if self.reverse_log_level_map.get(entry['level']) == level_filter_en
            ]

        if search_query:
            filtered_log_entries = [
                entry for entry in filtered_log_entries 
                if search_query in entry['message'].lower() or search_query in entry['module'].lower()
            ]

        # Add Bootstrap specific class for styling based on level
        for entry in filtered_log_entries:
            if entry['level'] == 'エラー' or entry['level'] == '緊急':
                entry['level_class'] = 'table-danger'
            elif entry['level'] == '警告':
                entry['level_class'] = 'table-warning'
            elif entry['level'] == '情報':
                entry['level_class'] = 'table-info'
            elif entry['level'] == 'デバッグ':
                entry['level_class'] = 'table-secondary'
            else:
                entry['level_class'] = ''

        # Reverse the order to show newest logs first
        filtered_log_entries.reverse()
        
        return render(request, self.template_name, {
            'log_entries': filtered_log_entries,
            'log_file_exists': log_file_exists,
            'request_get': request.GET, # Added for filter form persistence
            'settings': settings, # Pass settings for log file path display
        })

    def _process_log_buffer(self, buffer, log_entries, log_pattern):
        if not buffer:
            return

        first_line = buffer[0]
        match = log_pattern.match(first_line)
        if match:
            data = match.groupdict()
            message = data['message'].strip()
            # Append subsequent lines to the message
            for extra_line in buffer[1:]:
                message += '\n' + extra_line.strip()

            log_entries.append({
                'level': self.log_level_map.get(data['level'], data['level']), # Map to Japanese
                'datetime': data['datetime'],
                'module': data['module'],
                'message': message,
            })
        else:
            # If the first line doesn't match the pattern (e.g., file started with partial traceback),
            # add it as a raw message.
            log_entries.append({
                'level': '不明',
                'datetime': '',
                'module': '',
                'message': "".join(buffer).strip(),
            })


class ConsentMyPageView(View):
    """
    組込み署名（SMS認証）/簡易認証の同意用マイページ。
    document_id と participant_id を受け取り、署名URLを取得して表示する。
    """
    template_name = 'projects/consent_mypage.html'

    def get(self, request, *args, **kwargs):
        document_id = request.GET.get('document_id')
        participant_id = request.GET.get('participant_id')
        recipient_id = request.GET.get('recipient_id')
        local_participant_id = request.GET.get('local_participant_id')

        if not document_id or not participant_id:
            messages.error(request, 'document_id と participant_id を指定してください。')
            return render(request, self.template_name, {
                'document_id': document_id,
                'participant_id': participant_id,
            })

        def resolve_participant_id():
            """
            参加者IDが不正/未設定の場合に、書類情報とローカル参加者情報から補完する。
            """
            if not local_participant_id:
                return None, None
            participant = Participant.objects.filter(id=local_participant_id).first()
            if not participant:
                return None, None
            try:
                client = CloudSignAPIClient()
                detail = client.get_document(document_id)
                candidates = detail.get('participants', [])
                match = None
                if participant.tel:
                    match = next((c for c in candidates if c.get('tel') == participant.tel), None)
                if match is None and participant.recipient_id:
                    match = next((c for c in candidates if c.get('recipient_id') == participant.recipient_id), None)
                if match is None and participant.email:
                    match = next((c for c in candidates if c.get('email') == participant.email), None)
                if match and match.get('id'):
                    participant.cloudsign_participant_id = match.get('id')
                    participant.save(update_fields=['cloudsign_participant_id'])
                    return participant.cloudsign_participant_id, participant
            except Exception as e:
                logger.warning(f"参加者IDの補完に失敗しました: {e}")
            return None, participant

        # 参加者IDが明らかに不正な場合は補完を試みる
        participant = None
        if participant_id == document_id:
            participant_id, participant = resolve_participant_id()

        # 受信者IDは保存済みの参加者情報から補完する
        if not participant:
            participant = Participant.objects.filter(cloudsign_participant_id=participant_id).first()
        if participant and participant.recipient_id:
            recipient_id = participant.recipient_id

        try:
            client = CloudSignAPIClient()
            if not participant_id:
                raise Exception("参加者IDが特定できませんでした。")
            signing_info = client.get_signing_url(document_id, participant_id, recipient_id=recipient_id)
            return render(request, self.template_name, {
                'document_id': document_id,
                'participant_id': participant_id,
                'signing_url': signing_info.get('url'),
                'expires_at': signing_info.get('expires_at'),
            })
        except Exception as e:
            messages.error(request, f'署名URLの取得に失敗しました: {e}')
            return render(request, self.template_name, {
                'document_id': document_id,
                'participant_id': participant_id,
            })


# --- New Unified Project Manage View ---
class ProjectManageView(View):
    template_name = 'projects/project_manage_form.html'

    def _get_send_mode(self, request):
        return request.POST.get('send_mode', 'normal')

    def _validate_participants_for_send_mode(self, participant_formset, send_mode):
        """
        送信種別ごとの必須項目をチェックする。
        """
        is_valid = True
        for form in participant_formset.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            if not form.cleaned_data or form.cleaned_data.get('DELETE', False):
                continue

            if send_mode == 'normal':
                if not form.cleaned_data.get('email'):
                    form.add_error('email', '通常送信ではメールアドレスが必須です。')
                    is_valid = False
            elif send_mode == 'embedded_sms':
                if not form.cleaned_data.get('tel'):
                    form.add_error('tel', '組込み署名（SMS認証）では電話番号が必須です。')
                    is_valid = False
            elif send_mode == 'simple_auth':
                if not form.cleaned_data.get('recipient_id'):
                    form.add_error('recipient_id', '簡易認証では受信者IDが必須です。')
                    is_valid = False
        return is_valid

    def get(self, request, pk=None):
        project = None
        if pk:
            project = get_object_or_404(Project, pk=pk)
        
        project_form = ProjectForm(instance=project)
        contract_file_formset = ContractFileFormSet(instance=project)
        participant_formset = ParticipantFormSet(instance=project)

        context = {
            'project_form': project_form,
            'contract_file_formset': contract_file_formset,
            'participant_formset': participant_formset,
            'project': project, # Pass project instance for template logic (e.g., title in header)
            'send_mode': project.send_method if project and project.send_method else 'normal',
        }
        return render(request, self.template_name, context)

    def post(self, request, pk=None):
        project = None
        if pk:
            project = get_object_or_404(Project, pk=pk)
        
        project_form = ProjectForm(request.POST, instance=project)
        contract_file_formset = ContractFileFormSet(request.POST, request.FILES, instance=project)
        participant_formset = ParticipantFormSet(request.POST, instance=project)

        send_mode = self._get_send_mode(request)

        context = {
            'project_form': project_form,
            'contract_file_formset': contract_file_formset,
            'participant_formset': participant_formset,
            'project': project,
            'send_mode': send_mode,
        }

        if project_form.is_valid() and contract_file_formset.is_valid() and participant_formset.is_valid():
            if 'save_and_send' in request.POST:
                if not self._validate_participants_for_send_mode(participant_formset, send_mode):
                    messages.error(request, "宛先情報に不足があります。")
                    return render(request, self.template_name, context)

            project = project_form.save()
            contract_file_formset.instance = project
            contract_file_formset.save()

            # --- ここに新しいログを追加 ---
            logger.debug(f"After contract_file_formset.save(): project.files.count()={project.files.count()}")
            for cf in project.files.all():
                logger.debug(f"  - ContractFile ID: {cf.id}, Name: {cf.file.name}, Size: {cf.file.size if cf.file else 'None'}")
            # --- ここまで新しいログを追加 ---

            participant_formset.instance = project
            participant_formset.save()

            # 送信種別に応じてコールバックフラグを保存
            if 'save_and_send' in request.POST:
                project.participants.update(callback=(send_mode == 'embedded_sms'))

            if 'save_and_send' in request.POST:
                # First, check for files and participants after saving
                if not project.files.exists():
                    messages.error(request, "CloudSignに送信するには、少なくとも1つのファイルが必要です。")
                    return render(request, self.template_name, context)

                if not project.participants.exists():
                    messages.error(request, "CloudSignに送信するには、少なくとも1人の宛先が必要です。")
                    return render(request, self.template_name, context)

                try:
                    client = CloudSignAPIClient() # Step 1: Get Access Token (implicitly handled)
                    
                    # Store existing CloudSign document ID if any
                    current_cloudsign_document_id = project.cloudsign_document_id

                    # Step 2: 書類の作成 (Create Document)
                    if not current_cloudsign_document_id:
                        # Call create_document with only title, as modified in CloudSignAPIClient
                        doc = client.create_document(project.title)
                        project.cloudsign_document_id = doc['id']
                        project.save()
                        messages.info(request, f"CloudSignドキュメント (ID: {project.cloudsign_document_id}) が作成されました。")
                        current_cloudsign_document_id = project.cloudsign_document_id
                    else:
                        # 既存ドキュメントが下書き以外の場合は送信を拒否（組込み署名はリマインド不可）
                        try:
                            existing_detail = client.get_document(current_cloudsign_document_id)
                            status = existing_detail.get('status')
                            if status is not None and status != 0:
                                messages.error(
                                    request,
                                    "既に送信済みの書類です。組込み署名（SMS認証）はリマインド不可のため再送できません。"
                                )
                                return render(request, self.template_name, context)
                        except Exception as e:
                            logger.warning(f"既存ドキュメントの状態取得に失敗しました: {e}")
                        # If document already exists, just update title. No files/parties in this call now.
                        client.update_document(current_cloudsign_document_id, {'title': project.title})
                    
                    # After document creation/update, ensure document_id exists
                    if not current_cloudsign_document_id:
                        raise Exception("CloudSignドキュメントIDが取得できませんでした。")

                    # Step 3: 書類への宛先の追加 (Add Recipient to Document)
                    # 既存の参加者のIDを取得して再追加を避ける
                    existing_cloudsign_participants_by_email = {}
                    try:
                        cloudsign_document_details = client.get_document(current_cloudsign_document_id)
                        for cs_participant in cloudsign_document_details.get('participants', []):
                            if cs_participant.get('email'):
                                existing_cloudsign_participants_by_email[cs_participant.get('email')] = cs_participant
                    except requests.exceptions.HTTPError as e:
                        logger.warning(f"CloudSignドキュメント {current_cloudsign_document_id} の既存の参加者の取得に失敗しました: {e.response.text}")
                    except Exception as e:
                        logger.warning(f"既存のCloudSign参加者の取得中に予期せぬエラーが発生しました: {e}")

                    participants_to_add_count = 0
                    for p in project.participants.all():
                        if p.cloudsign_participant_id:
                            continue

                        if p.email and p.email in existing_cloudsign_participants_by_email:
                            p.cloudsign_participant_id = existing_cloudsign_participants_by_email[p.email].get('id')
                            p.save(update_fields=['cloudsign_participant_id'])
                            continue

                        callback = True if send_mode == 'embedded_sms' else False
                        try:
                            participant_response = client.add_participant(
                                current_cloudsign_document_id,
                                name=p.name,
                                email=p.email,
                                tel=p.tel if send_mode == 'embedded_sms' else None,
                                recipient_id=p.recipient_id if send_mode == 'simple_auth' else None,
                                callback=callback,
                            )
                        except requests.exceptions.HTTPError as e:
                            # 組込み署名（SMS認証）はcallback=true必須のため、未許可時は明確にエラー化する
                            if send_mode == 'embedded_sms' and e.response is not None and 'forbidden to callback' in e.response.text:
                                raise Exception("CloudSign側のチーム設定で組込み署名（SMS認証）が有効ではありません。callback許可が必要です。")
                            raise
                        participants_to_add_count += 1

                        if isinstance(participant_response, dict) and participant_response.get('id'):
                            p.cloudsign_participant_id = participant_response.get('id')
                            p.save(update_fields=['cloudsign_participant_id'])
                        else:
                            # 参加者IDが返らない場合は書類情報から検索して補完する
                            try:
                                detail = client.get_document(current_cloudsign_document_id)
                                candidates = detail.get('participants', [])
                                match = None
                                if send_mode == 'embedded_sms' and p.tel:
                                    match = next((c for c in candidates if c.get('tel') == p.tel), None)
                                elif send_mode == 'simple_auth' and p.recipient_id:
                                    match = next((c for c in candidates if c.get('recipient_id') == p.recipient_id), None)
                                elif p.email:
                                    match = next((c for c in candidates if c.get('email') == p.email), None)

                                if match and match.get('id'):
                                    p.cloudsign_participant_id = match.get('id')
                                    p.save(update_fields=['cloudsign_participant_id'])
                                else:
                                    logger.info("CloudSign参加者IDが取得できなかったため、IDの保存をスキップしました。")
                            except Exception as e:
                                logger.info(f"CloudSign参加者IDの補完に失敗しました: {e}")
                    
                    if participants_to_add_count > 0:
                        messages.info(request, f"{participants_to_add_count}件の宛先がCloudSignドキュメントに追加されました。")

                    # Step 4: 書類へのPDFの追加 (Add PDF to Document)
                    # Fetch existing files on CloudSign to avoid re-uploading them.
                    existing_cloudsign_files_names = set()
                    # We need to re-fetch document details or ensure cloudsign_document_details is up-to-date
                    # For safety, let's re-fetch if we didn't get it or if it's stale after participant adds
                    cloudsign_document_details_after_adds = client.get_document(current_cloudsign_document_id)
                    for cs_file in cloudsign_document_details_after_adds.get('files', []):
                        existing_cloudsign_files_names.add(cs_file.get('name'))

                    files_to_add_count = 0
                    for local_file in project.files.all(): # Iterate through local files
                        if local_file.file.name not in existing_cloudsign_files_names:
                            client.add_file_to_document(
                                current_cloudsign_document_id,
                                local_file.file,
                                display_name=local_file.original_name or os.path.basename(local_file.file.name)
                            )
                            files_to_add_count += 1
                        else:
                            logger.info(f"File {local_file.file.name} already exists in CloudSign document {current_cloudsign_document_id}, skipping.")

                    if files_to_add_count > 0:
                        messages.info(request, f"{files_to_add_count}件のファイルがCloudSignドキュメントに追加されました。")
                    elif not project.files.exists() and not files_to_add_count:
                        # This should have been caught by the initial check, but as a fallback
                        raise Exception("CloudSignに送信するには、少なくとも1つのファイルが必要です。")

                    # Step 5: 書類の送信 (Send Document)
                    client.send_document(current_cloudsign_document_id)
                    
                    project.send_method = send_mode
                    project.save(update_fields=['send_method'])

                    messages.success(request, f"案件「{project.title}」が保存され、CloudSignで正常に送信されました。")

                except Exception as e:
                    messages.error(request, f"CloudSignへの送信中にエラーが発生しました: {e}")
                    return render(request, self.template_name, context)

                return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': project.pk}))
            else: # save_draft
                messages.success(request, "案件と関連データが下書きとして保存されました。")
                return redirect(reverse_lazy('projects:project_detail', kwargs={'pk': project.pk}))
        else:
            messages.error(request, "入力内容にエラーがあります。")
            return render(request, self.template_name, context)


class EmbeddedProjectCreateView(View):
    form_template_name = 'projects/embedded_project_form.html'
    success_url_name = 'projects:embedded_project_create_success'

    def get(self, request, *args, **kwargs):
        context = {
            'project_form': ProjectForm(),
            'contract_file_formset': ContractFileFormSet(prefix='files'),
            'participant_formset': EmbeddedParticipantFormSet(prefix='participants'),
            'title': '新規組み込み署名案件作成',
        }
        return render(request, self.form_template_name, context)

    def post(self, request, *args, **kwargs):
        project_form = ProjectForm(request.POST)
        contract_file_formset = ContractFileFormSet(request.POST, request.FILES, prefix='files')
        participant_formset = EmbeddedParticipantFormSet(request.POST, prefix='participants')

        context = {
            'project_form': project_form,
            'contract_file_formset': contract_file_formset,
            'participant_formset': participant_formset,
            'title': '新規組み込み署名案件作成',
        }

        if not (project_form.is_valid() and contract_file_formset.is_valid() and participant_formset.is_valid()):
            messages.error(request, "入力内容にエラーがあります。")
            return render(request, self.form_template_name, context)

        files = [
            form.cleaned_data['file']
            for form in contract_file_formset
            if form.cleaned_data.get('file') and not form.cleaned_data.get('DELETE')
        ]
        if not files:
            messages.error(request, "CloudSignドキュメント作成には、少なくとも1つのファイルが必要です。")
            return render(request, self.form_template_name, context)

        participants_data = [
            form.cleaned_data
            for form in participant_formset
            if form.cleaned_data and not form.cleaned_data.get('DELETE')
        ]
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
        participant_instances = participant_formset.save()

        try:
            client = CloudSignAPIClient()
            document_id, signing_urls, participants_with_cs_id = client.create_embedded_signing_document(
                title=project.title,
                files=files,
                participants_data=participants_data,
            )
            project.cloudsign_document_id = document_id
            project.save()

            participant_map = {p.email: p for p in participant_instances}
            for p_data in participants_with_cs_id:
                participant = participant_map.get(p_data.get('email'))
                if not participant:
                    continue
                participant.cloudsign_participant_id = p_data.get('cloudsign_participant_id')
                url_info = next(
                    (url for url in signing_urls if url.get('cloudsign_participant_id') == p_data.get('cloudsign_participant_id')),
                    None,
                )
                if url_info:
                    participant.signing_url = url_info.get('url')
                participant.save()

            request.session['embedded_project_id'] = project.id
            messages.success(request, "案件が作成され、組み込み署名URLが生成されました。")
            return redirect(self.success_url_name)
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}][post][Project: {project.id}] Error creating embedded signing document: {e}", exc_info=True)
            messages.error(request, f"CloudSign連携中にエラーが発生しました: {e}")
            project.delete()
            return render(request, self.form_template_name, context)


class EmbeddedProjectSuccessView(TemplateView):
    template_name = 'projects/embedded_project_success.html'

    def get(self, request, *args, **kwargs):
        project_id = request.session.pop('embedded_project_id', None)
        if not project_id:
            messages.warning(request, "表示する署名URL情報がありません。")
            return redirect(reverse_lazy('projects:project_list'))
        project = get_object_or_404(Project, pk=project_id)
        participants_with_urls = project.participants.filter(is_embedded_signer=True, signing_url__isnull=False)
        return render(request, self.template_name, {
            'project': project,
            'participants_with_urls': participants_with_urls,
        })


class SigningView(DetailView):
    model = Participant
    template_name = 'projects/signing_page.html'
    context_object_name = 'participant'
    slug_field = 'id'
    slug_url_kwarg = 'signer_id'

    def get_object(self, queryset=None):
        signer_id = self.kwargs.get(self.slug_url_kwarg)
        try:
            if isinstance(signer_id, str):
                UUID(signer_id)
        except (ValueError, TypeError):
            raise Http404("無効な署名者IDです。")
        return get_object_or_404(Participant, id=signer_id)
