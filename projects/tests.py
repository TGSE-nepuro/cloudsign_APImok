# -*- coding: utf-8 -*-
from django.test import TestCase, Client, override_settings
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, date
import json

from projects.cloudsign_api import CloudSignAPIClient
from projects.models import CloudSignConfig, Project, ContractFile
from django.urls import reverse, resolve
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext_lazy as _
from .forms import ProjectForm

class CloudSignAPIClientTests(TestCase):

    @patch('projects.models.CloudSignConfig.objects')
    def setUp(self, mock_cloudsign_config_objects):
        mock_config = MagicMock()
        mock_config.client_id = "test_client_id"
        mock_config.api_base_url = "https://api-sandbox.cloudsign.jp"
        mock_cloudsign_config_objects.first.return_value = mock_config

        CloudSignAPIClient._instance = None
        self.client = CloudSignAPIClient()

        self.client._initialized = False
        self.client.__init__()

        self.assertEqual(self.client.client_id, "test_client_id")
        self.assertEqual(self.client.api_base_url, "https://api-sandbox.cloudsign.jp")

    @patch('requests.post')
    def test_get_access_token_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response

        token = self.client._get_access_token()

        self.assertEqual(token, "test_access_token")
        self.assertEqual(self.client.access_token, "test_access_token")
        self.assertIsNotNone(self.client.token_expires_at)

        expected_url = "https://api-sandbox.cloudsign.jp/token"
        expected_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        expected_data = {
            "client_id": "test_client_id",
        }
        mock_post.assert_called_once_with(
            expected_url,
            headers=expected_headers,
            data=expected_data,
            timeout=10
        )

    @patch('requests.post')
    def test_get_access_token_refresh(self, mock_post):
        self.client.access_token = "expired_token"
        self.client.token_expires_at = datetime.now() - timedelta(minutes=5)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response

        token = self.client._get_access_token()

        self.assertEqual(token, "new_access_token")
        self.assertEqual(self.client.access_token, "new_access_token")
        self.assertIsNotNone(self.client.token_expires_at)
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_get_access_token_cached(self, mock_post):
        self.client.access_token = "valid_token"
        self.client.token_expires_at = datetime.now() + timedelta(minutes=30)

        token = self.client._get_access_token()

        self.assertEqual(token, "valid_token")
        self.assertEqual(self.client.access_token, "valid_token")
        self.assertIsNotNone(self.client.token_expires_at)
        mock_post.assert_not_called()

    @patch('requests.request')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_create_document_success(self, mock_get_access_token, mock_request):
        mock_get_access_token.return_value = "dummy_access_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "doc_id_123", "title": "Test Document"}
        mock_request.return_value = mock_response

        mock_file = SimpleUploadedFile("test_file.pdf", b"pdf_content", content_type="application/pdf")

        title = "My Test Document"
        files = [mock_file]
        response_data = self.client.create_document(title, files=files)

        self.assertEqual(response_data, {"id": "doc_id_123", "title": "Test Document"})
        mock_get_access_token.assert_called_once()
        mock_request.assert_called_once()
        call_args, call_kwargs = mock_request.call_args
        self.assertEqual(call_args[0], "POST")

    @patch('requests.request')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_get_document_success(self, mock_get_access_token, mock_request):
        mock_get_access_token.return_value = "dummy_access_token"
        expected_document_data = {"id": "doc_id_123", "title": "Test Document", "status": 0}
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = expected_document_data
        mock_request.return_value = mock_response

        document_id = "doc_id_123"
        response_data = self.client.get_document(document_id)

        self.assertEqual(response_data, expected_document_data)
        mock_get_access_token.assert_called_once()
        mock_request.assert_called_once()
        call_args, call_kwargs = mock_request.call_args
        self.assertEqual(call_args[0], "GET")
        self.assertEqual(call_args[1], f"https://api-sandbox.cloudsign.jp/documents/{document_id}")

    @patch('requests.request')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_add_participant_success(self, mock_get_access_token, mock_request):
        mock_get_access_token.return_value = "dummy_access_token"
        expected_response_data = {"id": "doc_id_123", "participants": [{"email": "test@example.com", "name": "Test User"}]}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response_data
        mock_request.return_value = mock_response

        document_id = "doc_id_123"
        email = "test@example.com"
        name = "Test User"

        response_data = self.client.add_participant(document_id, email, name)

        self.assertEqual(response_data, expected_response_data)
        mock_get_access_token.assert_called_once()
        mock_request.assert_called_once()
        call_args, call_kwargs = mock_request.call_args
        self.assertEqual(call_args[0], "POST")
        self.assertEqual(call_args[1], f"https://api-sandbox.cloudsign.jp/documents/{document_id}/participants")

    @patch('requests.request')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_update_document_success(self, mock_get_access_token, mock_request):
        mock_get_access_token.return_value = "dummy_access_token"
        expected_response_data = {"id": "doc_id_123", "title": "Updated Title", "status": 0}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = expected_response_data
        mock_request.return_value = mock_response

        document_id = "doc_id_123"
        update_data = {"title": "Updated Title", "note": "Some note"}
        response_data = self.client.update_document(document_id, update_data)

        self.assertEqual(response_data, expected_response_data)
        mock_get_access_token.assert_called_once()
        mock_request.assert_called_once()
        call_args, call_kwargs = mock_request.call_args
        self.assertEqual(call_args[0], "PUT")
        self.assertEqual(call_args[1], f"https://api-sandbox.cloudsign.jp/documents/{document_id}")




class CloudSignConfigViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('projects:cloudsign_config')

    def test_get_config_page_no_config(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/cloudsignconfig_form.html')
        self.assertIn('form', response.context)
        self.assertIsNone(response.context['form'].instance.pk)

    def test_get_config_page_with_config(self):
        CloudSignConfig.objects.create(client_id="existing_id", api_base_url="https://existing.api")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/cloudsignconfig_form.html')
        self.assertIn('form', response.context)
        self.assertEqual(response.context['form'].instance.client_id, "existing_id")

    def test_post_create_config_success(self):
        self.assertEqual(CloudSignConfig.objects.count(), 0)
        post_data = {'client_id': 'new_client_id', 'api_base_url': 'https://new.api'}
        response = self.client.post(self.url, post_data, follow=True)
        self.assertRedirects(response, self.url)
        self.assertEqual(CloudSignConfig.objects.count(), 1)
        config = CloudSignConfig.objects.first()
        self.assertEqual(config.client_id, 'new_client_id')
        messages_list = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages_list), 1)
        self.assertEqual(str(messages_list[0]), "CloudSign設定が正常に更新されました。")

    def test_post_update_config_success(self):
        CloudSignConfig.objects.create(client_id="old_id", api_base_url="https://old.api")
        post_data = {'client_id': 'updated_id', 'api_base_url': 'https://updated.api'}
        response = self.client.post(self.url, post_data, follow=True)
        self.assertRedirects(response, self.url)
        self.assertEqual(CloudSignConfig.objects.count(), 1)
        config = CloudSignConfig.objects.first()
        self.assertEqual(config.client_id, 'updated_id')
        messages_list = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages_list), 1)
        self.assertEqual(str(messages_list[0]), "CloudSign設定が正常に更新されました。")

    def test_post_create_config_invalid_data(self):
        post_data = {'client_id': '', 'api_base_url': 'invalid-url'}
        response = self.client.post(self.url, post_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertContains(response, "Enter a valid URL.")
        self.assertEqual(CloudSignConfig.objects.count(), 0)

    def test_delete_button_not_present_when_no_config(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, reverse('projects:cloudsign_config_delete'))

    def test_delete_button_present_when_config_exists(self):
        CloudSignConfig.objects.create(client_id="test_id")
        response = self.client.get(self.url)
        self.assertContains(response, reverse('projects:cloudsign_config_delete'))



class CloudSignConfigDeleteViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.config = CloudSignConfig.objects.create(client_id="test-id-to-delete")
        self.url = reverse('projects:cloudsign_config_delete')
        self.success_url = reverse('projects:cloudsign_config')

    def test_get_delete_confirmation_page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/cloudsignconfig_confirm_delete.html')
        self.assertContains(response, 'Are you sure you want to delete this configuration?')

    def test_post_deletes_config(self):
        self.assertEqual(CloudSignConfig.objects.count(), 1)
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, self.success_url)
        self.assertEqual(CloudSignConfig.objects.count(), 0)
        self.assertContains(response, "CloudSign設定が正常に削除されました。")

    def test_delete_view_redirects_if_no_config(self):
        self.config.delete()
        self.assertEqual(CloudSignConfig.objects.count(), 0)
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(response, self.success_url)
        self.assertContains(response, "削除する設定がありません。")


class ProjectManageViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.create_url = reverse('projects:project_manage_new')
        self.project = Project.objects.create(title="Existing Project")
        self.update_url = reverse('projects:project_manage_edit', kwargs={'pk': self.project.pk})

    def test_get_create_view(self):
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/project_manage_form.html')
        self.assertIn('project_form', response.context)
        self.assertIn('contract_file_formset', response.context)
        self.assertIn('participant_formset', response.context)
        self.assertContains(response, '新規案件作成')

    def test_get_update_view(self):
        response = self.client.get(self.update_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/project_manage_form.html')
        self.assertEqual(response.context['project_form'].instance, self.project)
        self.assertContains(response, '案件編集')

    def test_post_create_draft(self):
        project_data = {
            'title': 'New Draft Project',
            'description': 'A draft description.',
            'participants-TOTAL_FORMS': '1',
            'participants-INITIAL_FORMS': '0',
            'participants-MIN_NUM_FORMS': '0',
            'participants-MAX_NUM_FORMS': '1000',
            'participants-0-name': 'John Doe',
            'participants-0-email': 'john.doe@example.com',
            'participants-0-order': '0',
            'files-TOTAL_FORMS': '0',
            'files-INITIAL_FORMS': '0',
            'files-MIN_NUM_FORMS': '0',
            'files-MAX_NUM_FORMS': '1000',
            'save_draft': '' #下書き保存ボタンが押されたことを示す
        }
        response = self.client.post(self.create_url, project_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        new_project = Project.objects.get(title='New Draft Project')
        self.assertIsNotNone(new_project)
        self.assertEqual(new_project.participants.count(), 1)
        self.assertEqual(new_project.participants.first().name, 'John Doe')
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "案件と関連データが下書きとして保存されました。")

    @patch('projects.views.CloudSignAPIClient')
    def test_post_create_and_send_success(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.create_document.return_value = {'id': 'new_doc_id'}
        
        # Prepare a dummy file for upload
        dummy_file = SimpleUploadedFile("test_contract.pdf", b"file content", content_type="application/pdf")
        
        project_data = {
            'title': 'New Sent Project',
            'description': 'A sent description.',
            'participants-TOTAL_FORMS': '1',
            'participants-INITIAL_FORMS': '0',
            'participants-0-name': 'Jane Doe',
            'participants-0-email': 'jane.doe@example.com',
            'participants-0-order': '0',
            'files-TOTAL_FORMS': '1',
            'files-INITIAL_FORMS': '0',
            'files-0-file': dummy_file,
            'save_and_send': '' 
        }

        response = self.client.post(self.create_url, project_data, follow=True)
        
        self.assertEqual(response.status_code, 200)
        
        new_project = Project.objects.get(title='New Sent Project')
        self.assertEqual(new_project.cloudsign_document_id, 'new_doc_id')

        mock_api_instance.create_document.assert_called_once()
        mock_api_instance.add_participant.assert_called_once_with('new_doc_id', 'jane.doe@example.com', 'Jane Doe')
        mock_api_instance.send_document.assert_called_once_with('new_doc_id', {})

        messages = list(response.context['messages'])
        self.assertTrue(any("正常に送信されました" in str(m) for m in messages))

    def test_post_create_and_send_no_files(self):
        project_data = {
            'title': 'Project without files',
            'participants-TOTAL_FORMS': '1',
            'participants-INITIAL_FORMS': '0',
            'participants-0-name': 'Test',
            'participants-0-email': 'test@test.com',
            'participants-0-order': '0',
            'files-TOTAL_FORMS': '1',
            'files-INITIAL_FORMS': '0',
            'files-0-file': '',
            'files-0-id': '',
            'save_and_send': ''
        }
        response = self.client.post(self.create_url, project_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CloudSignに送信するには、少なくとも1つのファイルが必要です。")

    def test_post_create_and_send_no_participants(self):
        dummy_file = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")
        project_data = {
            'title': 'Project without participants',
            'participants-TOTAL_FORMS': '0',
            'participants-INITIAL_FORMS': '0',
            'files-TOTAL_FORMS': '1',
            'files-INITIAL_FORMS': '0',
            'files-0-file': dummy_file,
            'save_and_send': ''
        }
        response = self.client.post(self.create_url, project_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CloudSignに送信するには、少なくとも1人の宛先が必要です。")

@patch('projects.views.CloudSignAPIClient')
class ProjectDetailViewTests(TestCase):
    def setUp(self):
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.client = Client()

    def test_project_detail_view_shows_participants(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.get_document.return_value = {
            "id": "doc_id_with_participants",
            "status": 1,  # "先方確認中"
            "participants": [
                {"email": "participant1@example.com", "name": "Participant One"},
                {"email": "participant2@example.com", "name": "Participant Two"}
            ]
        }

        project = Project.objects.create(title="Project with Participants", description="Description", cloudsign_document_id="doc_id_with_participants")
        detail_url = reverse('projects:project_detail', kwargs={'pk': project.pk})

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/project_detail.html')
        self.assertIn('cloudsign_participants', response.context)
        self.assertEqual(len(response.context['cloudsign_participants']), 2)
        
        # Verify status text
        self.assertContains(response, "先方確認中")

        # Verify participant text
        self.assertEqual(response.context['cloudsign_participants'][0]['name'], "Participant One")
        self.assertContains(response, "Participant One (participant1@example.com)")
        self.assertContains(response, "Participant Two (participant2@example.com)")
        
        mock_api_instance.get_document.assert_called_once_with(project.cloudsign_document_id)

@patch('projects.views.CloudSignAPIClient')
class DocumentSendViewTests(TestCase):
    def setUp(self):
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.project = Project.objects.create(title="Project for Sending", description="Description for send test", cloudsign_document_id="doc_id_for_send_test")
        self.client = Client()
        self.send_document_url = reverse('projects:send_document', kwargs={'pk': self.project.pk})

    def test_post_send_document_success(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.send_document.return_value = {"status": "sent"}
        response = self.client.post(self.send_document_url, follow=True)
        mock_api_instance.send_document.assert_called_once_with(document_id=self.project.cloudsign_document_id, send_data={})
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': self.project.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), f"CloudSignドキュメント (ID: {self.project.cloudsign_document_id}) が正常に送信されました。")

    def test_post_send_document_api_error(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.send_document.side_effect = Exception("API Send Error")
        response = self.client.post(self.send_document_url, follow=True)
        mock_api_instance.send_document.assert_called_once()
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': self.project.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("CloudSignドキュメントの送信に失敗しました: 予期せぬエラー: API Send Error", str(messages[0]))

    def test_post_send_document_no_cloudsign_document_id(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        project_no_doc_id = Project.objects.create(title="Project No Doc ID for Send", description="Description", cloudsign_document_id="")
        send_document_url_no_doc_id = reverse('projects:send_document', kwargs={'pk': project_no_doc_id.pk})
        response = self.client.post(send_document_url_no_doc_id, follow=True)
        mock_api_instance.send_document.assert_not_called()
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': project_no_doc_id.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "CloudSignドキュメントIDがないため、ドキュメントを送信できません。")


@patch('projects.views.CloudSignAPIClient')
class DocumentDownloadViewTests(TestCase):
    def setUp(self):
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.project = Project.objects.create(title="Project for Download", description="Description for download test", cloudsign_document_id="doc_id_for_download_test")
        self.client = Client()
        self.download_document_url = reverse('projects:download_document', kwargs={'pk': self.project.pk})

    def test_get_download_document_success(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.download_document.return_value = b"This is a test PDF content."
        response = self.client.get(self.download_document_url)
        mock_api_instance.download_document.assert_called_once_with(self.project.cloudsign_document_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(f'attachment; filename="cloudsign_document_{self.project.cloudsign_document_id}.pdf"', response['Content-Disposition'])
        self.assertEqual(response.content, b"This is a test PDF content.")

    def test_get_download_document_api_error(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.download_document.side_effect = Exception("API Download Error")
        response = self.client.get(self.download_document_url, follow=True)
        mock_api_instance.download_document.assert_called_once()
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': self.project.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("CloudSignドキュメントのダウンロードに失敗しました: 予期せぬエラー: API Download Error", str(messages[0]))

    def test_get_download_document_no_cloudsign_document_id(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        project_no_doc_id = Project.objects.create(title="Project No Doc ID for Download", description="Description", cloudsign_document_id="")
        download_document_url_no_doc_id = reverse('projects:download_document', kwargs={'pk': project_no_doc_id.pk})
        response = self.client.get(download_document_url_no_doc_id, follow=True)
        mock_api_instance.download_document.assert_not_called()
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': project_no_doc_id.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "CloudSignドキュメントIDがないため、ドキュメントをダウンロードできません。")

class ProjectListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.list_url = reverse('projects:project_list')
        # Create 15 projects to test pagination
        for i in range(15):
            Project.objects.create(
                title=f'Test Project {i}',
                description=f'This is a description for project {i}.',
                due_date=date(2023, 1, i + 1)
            )

    def test_pagination_displays_10_projects(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/project_list.html')
        self.assertEqual(len(response.context['projects']), 10)
        self.assertTrue(response.context['is_paginated'])

    def test_pagination_second_page(self):
        response = self.client.get(self.list_url, {'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/project_list.html')
        self.assertEqual(len(response.context['projects']), 5)

    def test_search_by_title(self):
        response = self.client.get(self.list_url, {'search': 'Project 1'})
        self.assertEqual(response.status_code, 200)
        # Should find 'Project 1' and 'Project 10' through 'Project 14'
        self.assertEqual(len(response.context['projects']), 6)
        self.assertContains(response, 'Test Project 1')
        self.assertNotContains(response, 'Test Project 2')

    def test_search_by_description(self):
        response = self.client.get(self.list_url, {'search': 'description for project 5'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['projects']), 1)
        self.assertContains(response, 'Test Project 5')

    def test_search_no_results(self):
        response = self.client.get(self.list_url, {'search': 'nonexistent query'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['projects']), 0)
        self.assertContains(response, "該当する案件がありません。")

    def test_search_retains_query_in_input(self):
        search_query = "search query"
        response = self.client.get(self.list_url, {'search': search_query})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{search_query}"')

    def test_filter_by_due_date(self):
        response = self.client.get(self.list_url, {'date_from': '2023-01-05', 'date_to': '2023-01-10'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['projects']), 6)
        self.assertContains(response, 'Test Project 4') # due_date=2023-01-05
        self.assertContains(response, 'Test Project 9') # due_date=2023-01-10
        self.assertNotContains(response, 'Test Project 3')
        self.assertNotContains(response, 'Test Project 10')

class ProjectFormTests(TestCase):
    def test_amount_field_with_commas(self):
        form_data = {
            'title': 'Test Project',
            'description': 'Test Description',
            'amount': '1,234,567'
        }
        form = ProjectForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['amount'], 1234567)

    def test_amount_field_invalid_characters(self):
        form_data = {
            'title': 'Test Project',
            'description': 'Test Description',
            'amount': '1,234,abc'
        }
        form = ProjectForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
        self.assertEqual(form.errors['amount'][0], "有効な数値を入力してください。")

from unittest.mock import patch, MagicMock, mock_open

class LogViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.log_url = reverse('projects:log_view')

    def test_log_view_displays_log_content(self):
        """
        Tests that the view correctly displays log content when the log file exists.
        Mocks are scoped using context managers and a specific patch target for robust isolation.
        """
        with patch('os.path.exists', return_value=True) as mock_exists:
            with patch('projects.views.open', mock_open(read_data="INFO 2023-10-27 Test Log Message")) as mock_file:
                response = self.client.get(self.log_url)
                
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'projects/log_view.html')
                self.assertContains(response, "INFO 2023-10-27 Test Log Message")
                mock_exists.assert_called_once()
                mock_file.assert_called_once()

    def test_log_view_file_not_found(self):
        """
        Tests that the view shows a 'file not found' message when the log file doesn't exist.
        Mocks are scoped using context managers and a specific patch target for robust isolation.
        """
        with patch('os.path.exists', return_value=False) as mock_exists:
            with patch('projects.views.open') as mock_file:
                response = self.client.get(self.log_url)
                
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'projects/log_view.html')
                
                self.assertIn("ログファイルが存在しません。", response.content.decode('utf-8'))
                mock_exists.assert_called_once()
                mock_file.assert_not_called()


