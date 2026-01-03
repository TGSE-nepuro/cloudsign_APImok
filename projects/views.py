from django.views.generic import ListView, DetailView, View, TemplateView
from django.views.generic.edit import UpdateView, CreateView, FormView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import models
from .models import Project, CloudSignConfig, ContractFile, Participant
from .forms import CloudSignConfigForm, ProjectForm, ContractFileFormSet, ParticipantFormSet
from .cloudsign_api import CloudSignAPIClient
import logging
import requests
import os
from django.conf import settings
from django.http import HttpResponse

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
            # The API might require a list of participants to send, but for now we assume
            # it sends to all existing participants.
            client.send_document(
                document_id=project.cloudsign_document_id,
                send_data={}
            )
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
            file_content = client.download_document(project.cloudsign_document_id)

            # Assuming the file is a PDF for now. A more robust implementation might
            # check the Content-Type header from the API response.
            response = HttpResponse(file_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="cloudsign_document_{project.cloudsign_document_id}.pdf"'
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
    Displays the content of the debug log file.
    """
    template_name = 'projects/log_view.html'

    def get(self, request, *args, **kwargs):
        log_file_path = settings.LOG_DIR / 'debug.log'
        log_content = "ログファイルが存在しません。"
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
        return render(request, self.template_name, {'log_content': log_content})


# --- New Unified Project Manage View ---
class ProjectManageView(View):
    template_name = 'projects/project_manage_form.html'

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
        }
        return render(request, self.template_name, context)

    def post(self, request, pk=None):
        project = None
        if pk:
            project = get_object_or_404(Project, pk=pk)
        
        project_form = ProjectForm(request.POST, instance=project)
        contract_file_formset = ContractFileFormSet(request.POST, request.FILES, instance=project)
        participant_formset = ParticipantFormSet(request.POST, instance=project)

        context = {
            'project_form': project_form,
            'contract_file_formset': contract_file_formset,
            'participant_formset': participant_formset,
            'project': project,
        }

        if project_form.is_valid() and contract_file_formset.is_valid() and participant_formset.is_valid():
            project = project_form.save()
            contract_file_formset.instance = project
            contract_file_formset.save()
            participant_formset.instance = project
            participant_formset.save()

            if 'save_and_send' in request.POST:
                # First, check for files and participants after saving
                if not project.files.exists():
                    messages.error(request, "CloudSignに送信するには、少なくとも1つのファイルが必要です。")
                    return render(request, self.template_name, context)

                if not project.participants.exists():
                    messages.error(request, "CloudSignに送信するには、少なくとも1人の宛先が必要です。")
                    return render(request, self.template_name, context)

                try:
                    client = CloudSignAPIClient()
                    all_files = [f.file for f in project.files.all()]
                    
                    # 1. Create or Update Document
                    if not project.cloudsign_document_id:
                        doc = client.create_document(project.title, files=all_files)
                        project.cloudsign_document_id = doc['id']
                        project.save()
                        messages.info(request, f"CloudSignドキュメント (ID: {project.cloudsign_document_id}) が作成されました。")
                    else:
                        client.update_document(project.cloudsign_document_id, {'title': project.title})

                    # 2. Add Participants
                    participants = project.participants.all()
                    for p in participants:
                        client.add_participant(project.cloudsign_document_id, p.email, p.name)
                    
                    # 3. Send Document
                    client.send_document(project.cloudsign_document_id)
                    
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