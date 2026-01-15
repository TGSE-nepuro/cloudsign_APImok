# -*- coding: utf-8 -*-
from django.test import TestCase, Client, override_settings
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, date
import os
import requests # Added for RequestException

from projects.cloudsign_api import CloudSignAPIClient
from projects.models import CloudSignConfig, Project, ContractFile, Participant
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

    @patch('projects.cloudsign_api.CloudSignAPIClient._make_authenticated_request') # Mock the internal request method
    def test_create_document_success(self, mock_make_authenticated_request):
        mock_make_authenticated_request.return_value = {"id": "doc_id_123", "title": "Test Document"}

        title = "My Test Document"
        response_data = self.client.create_document(title)

        self.assertEqual(response_data, {"id": "doc_id_123", "title": "Test Document"})
        mock_make_authenticated_request.assert_called_once()
        call_args, call_kwargs = mock_make_authenticated_request.call_args
        self.assertEqual(call_args[0], "POST")
        self.assertEqual(call_args[1], f"/documents") # Endpoint only, base URL is handled by the real _make_authenticated_request
        expected_data = {
            'title': title,
            'send_to_parties': False,
        }
        self.assertEqual(call_kwargs['data'], expected_data)

    @patch('projects.cloudsign_api.CloudSignAPIClient._make_authenticated_request') # Mock the internal request method
    def test_get_document_success(self, mock_make_authenticated_request):
        expected_document_data = {"id": "doc_id_123", "title": "Test Document", "status": 0}
        
        mock_make_authenticated_request.return_value = expected_document_data

        document_id = "doc_id_123"
        response_data = self.client.get_document(document_id)

        self.assertEqual(response_data, expected_document_data)
        mock_make_authenticated_request.assert_called_once()
        call_args, call_kwargs = mock_make_authenticated_request.call_args
        self.assertEqual(call_args[0], "GET")
        self.assertEqual(call_args[1], f"/documents/{document_id}")

    @patch('projects.cloudsign_api.CloudSignAPIClient._make_authenticated_request') # Mock the internal request method
    def test_add_participant_success(self, mock_make_authenticated_request):
        # The mock response should be what add_participant expects to parse
        mock_make_authenticated_request.return_value = {
            "id": "doc_id_123",
            "participants": [
                {"email": "test@example.com", "name": "Test User", "id": "test_participant_id"}
            ]
        }

        document_id = "doc_id_123"
        email = "test@example.com"
        name = "Test User"
        recipient_id = "rec_123" # Added for testing

        # Now add_participant returns the extracted participant ID
        new_participant_id = self.client.add_participant(document_id, email, name, recipient_id=recipient_id, callback=False)

        self.assertEqual(new_participant_id, "test_participant_id") # Assert only the ID
        mock_make_authenticated_request.assert_called_once()
        call_args, call_kwargs = mock_make_authenticated_request.call_args
        self.assertEqual(call_args[0], "POST")
        self.assertEqual(call_args[1], f"/documents/{document_id}/participants")
        self.assertEqual(call_kwargs['data']['email'], email)
        self.assertEqual(call_kwargs['data']['name'], name)
        self.assertEqual(call_kwargs['data']['recipient_id'], recipient_id)
        self.assertNotIn('callback', call_kwargs['data'])

    @patch('projects.cloudsign_api.CloudSignAPIClient._make_authenticated_request') # Mock the internal request method
    def test_update_document_success(self, mock_make_authenticated_request):
        expected_response_data = {"id": "doc_id_123", "title": "Updated Title", "status": 0}

        mock_make_authenticated_request.return_value = expected_response_data

        document_id = "doc_id_123"
        update_data = {"title": "Updated Title", "note": "Some note"}
        response_data = self.client.update_document(document_id, update_data)

        self.assertEqual(response_data, expected_response_data)
        mock_make_authenticated_request.assert_called_once()
        call_args, call_kwargs = mock_make_authenticated_request.call_args
        self.assertEqual(call_args[0], "PUT")
        self.assertEqual(call_args[1], f"/documents/{document_id}")

    @patch('projects.cloudsign_api.CloudSignAPIClient._make_authenticated_request') # Mock the internal request method
    def test_get_embedded_signing_url_success(self, mock_make_authenticated_request):
        expected_signing_info = {
            "url": "https://embedded.cloudsign.jp/signing/some_url",
            "expires_at": "2026-01-08T12:00:00Z"
        }
        mock_make_authenticated_request.return_value = expected_signing_info

        document_id = "doc_id_123"
        participant_id = "part_id_456"
        recipient_id = "rec_id_789"

        signing_info = self.client.get_embedded_signing_url(document_id, participant_id, recipient_id)

        self.assertEqual(signing_info, expected_signing_info)
        mock_make_authenticated_request.assert_called_once_with(
            "POST",
            f"/documents/{document_id}/participants/{participant_id}/signing_url",
            data={'recipient_id': recipient_id}
        )

    @patch('projects.cloudsign_api.CloudSignAPIClient.create_document')
    @patch('projects.cloudsign_api.CloudSignAPIClient.add_participant')
    @patch('projects.cloudsign_api.CloudSignAPIClient.add_file_to_document')
    @patch('projects.cloudsign_api.CloudSignAPIClient.get_embedded_signing_url')
    @patch('projects.cloudsign_api.CloudSignAPIClient.get_document')
    def test_create_embedded_signing_document_full_flow_success(self, mock_get_document, mock_get_embedded_signing_url, mock_add_file_to_document, mock_add_participant, mock_create_document):
        # Mock responses for each step of the flow
        mock_create_document.return_value = {"id": "new_embedded_doc_id", "title": "Embedded Doc Title"}
        mock_add_participant.side_effect = ["participant_id_1", "participant_id_2", "participant_id_3"] # Three participants
        mock_add_file_to_document.return_value = {"id": "file_id_1"}
        mock_get_embedded_signing_url.side_effect = [
            {"url": "https://embedded.cloudsign.jp/signer1_url", "expires_at": "2026-01-09T10:00:00Z"},
            {"url": "https://embedded.cloudsign.jp/signer2_url", "expires_at": "2026-01-09T10:00:00Z"}
        ]
        mock_get_document.return_value = {'id': 'new_embedded_doc_id', 'participants': [], 'files': []} # For internal checks if any

        # Test data
        title = "Test Embedded Project"
        files = [SimpleUploadedFile("file1.pdf", b"pdf_content")]
        participants_data = [
            {'name': 'Signer One', 'email': 'signer1@example.com', 'tel': '09012345678', 'is_embedded_signer': True},
            {'name': 'Signer Two', 'email': 'signer2@example.com', 'tel': '09087654321', 'is_embedded_signer': True},
            {'name': 'Watcher', 'email': 'watcher@example.com', 'is_embedded_signer': False}
        ]

        # Call the method we are testing
        returned_document_id, returned_signing_urls_info, returned_all_participants = self.client.create_embedded_signing_document(
            title, files, participants_data
        )

        self.assertEqual(returned_document_id, "new_embedded_doc_id")
        self.assertEqual(len(returned_signing_urls_info), 2)
        self.assertEqual(returned_signing_urls_info[0]['url'], "https://embedded.cloudsign.jp/signer1_url")
        self.assertEqual(returned_signing_urls_info[1]['url'], "https://embedded.cloudsign.jp/signer2_url")

        self.assertEqual(len(returned_all_participants), 3)
        self.assertEqual(returned_all_participants[0]['cloudsign_participant_id'], "participant_id_1")
        self.assertEqual(returned_all_participants[1]['cloudsign_participant_id'], "participant_id_2")
        self.assertEqual(returned_all_participants[2]['cloudsign_participant_id'], "participant_id_3")


        # Simulate create_document
        mock_create_document.assert_called_once_with(title)
        
        # Simulate add_file_to_document
        mock_add_file_to_document.assert_called_once_with(returned_document_id, files[0])

        # Simulate add_participant and get_embedded_signing_url for embedded signers
        # Check calls for each participant
        mock_add_participant.assert_any_call(
            returned_document_id, 'signer1@example.com', 'Signer One', tel='09012345678', callback=True
        )
        mock_add_participant.assert_any_call(
            returned_document_id, 'signer2@example.com', 'Signer Two', tel='09087654321', callback=True
        )
        mock_add_participant.assert_any_call(
            returned_document_id, 'watcher@example.com', 'Watcher', recipient_id=None
        )
        self.assertEqual(mock_add_participant.call_count, 3)

        mock_get_embedded_signing_url.assert_any_call(
            returned_document_id, "participant_id_1"
        )
        mock_get_embedded_signing_url.assert_any_call(
            returned_document_id, "participant_id_2"
        )
        self.assertEqual(mock_get_embedded_signing_url.call_count, 2)

        # The actual method call and its return will be tested once it's implemented.
        # For now, this test primarily verifies the internal API calls.

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
        mock_api_instance.create_document.return_value = {'id': 'new_doc_id', 'title': 'New Sent Project'}
        mock_api_instance.get_document.return_value = {'id': 'new_doc_id', 'participants': [], 'files': []}
        mock_api_instance.add_participant.return_value = "mock_cloudsign_part_id" # Set return value
        
        # Prepare a dummy file for upload with Japanese characters
        japanese_filename = "日本語の契約書.pdf"
        dummy_file = SimpleUploadedFile(japanese_filename, b"file content", content_type="application/pdf")
        
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
        self.assertEqual(new_project.participants.first().cloudsign_participant_id, "mock_cloudsign_part_id") # Verify saved ID

        mock_api_instance.create_document.assert_called_once_with('New Sent Project')
        mock_api_instance.get_document.assert_called() # Called multiple times for participants and files
        mock_api_instance.add_participant.assert_called_once_with(
            'new_doc_id', 'jane.doe@example.com', 'Jane Doe', recipient_id=None # Updated expected args
        )
        
        # Assert add_file_to_document call
        mock_api_instance.add_file_to_document.assert_called_once()
        call_args, call_kwargs = mock_api_instance.add_file_to_document.call_args
        self.assertEqual(call_args[0], 'new_doc_id') # First argument is document_id
        passed_file_obj = call_args[1]
        
        # Extract base name and extension from the original Japanese filename for comparison
        expected_base_name, expected_ext = os.path.splitext(japanese_filename)
        actual_filename_basename = os.path.basename(passed_file_obj.name)

        # Assert that the actual filename starts with the expected base name and ends with the expected extension
        self.assertTrue(actual_filename_basename.startswith(expected_base_name))
        self.assertTrue(actual_filename_basename.endswith(expected_ext))

        passed_file_obj.seek(0)
        self.assertEqual(passed_file_obj.read(), b"file content") # Check file content

        mock_api_instance.send_document.assert_called_once_with('new_doc_id')

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
    def test_send_button_is_disabled_for_sent_document(self, MockCloudSignAPIClient):
        """
        Tests that the 'Save and Send' button is disabled if the document is already sent.
        """
        mock_api_instance = MockCloudSignAPIClient.return_value
        # 1: 先方確認中 (Awaiting partner's confirmation) - considered as "sent"
        mock_api_instance.get_document.return_value = {'status': 1}

        self.project.cloudsign_document_id = 'sent_doc_id'
        self.project.save()

        update_url = reverse('projects:project_manage_edit', kwargs={'pk': self.project.pk})
        response = self.client.get(update_url)

        self.assertEqual(response.status_code, 200)
        mock_api_instance.get_document.assert_called_once_with('sent_doc_id')
        # Check that the button is present and disabled
        self.assertContains(
            response,
            '<button type="submit" name="save_and_send" class="btn btn-success" disabled',
            html=False
        )


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

    def test_detail_view_button_visibility(self, MockCloudSignAPIClient):
        """
        Tests the visibility of 'Status Update' and 'Get Contract' buttons.
        """
        mock_api_instance = MockCloudSignAPIClient.return_value

        with self.subTest("Project without cloudsign_document_id"):
            project_no_cs = Project.objects.create(title="No CS ID")
            detail_url = reverse('projects:project_detail', kwargs={'pk': project_no_cs.pk})
            response = self.client.get(detail_url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "ステータスを更新")
            self.assertNotContains(response, "契約書を取得")

        with self.subTest("Project with CS ID and status 'Concluded'"):
            project_cs = Project.objects.create(title="With CS ID", cloudsign_document_id="doc_123")
            mock_api_instance.get_document.return_value = {
                "id": "doc_123",
                "status": 2,  # 締結済 (Corrected based on CloudSign API spec)
                "participants": []
            }
            detail_url = reverse('projects:project_detail', kwargs={'pk': project_cs.pk})
            response = self.client.get(detail_url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "ステータスを更新")
            self.assertContains(response, "契約書を取得")
            # The status text should also be visible
            self.assertContains(response, "締結済")

        with self.subTest("Project with CS ID and status not 'Concluded'"):
            # Re-use the same project, just change the mock return value
            mock_api_instance.get_document.return_value = {
                "id": "doc_123",
                "status": 1,  # 先方確認中
                "participants": []
            }
            detail_url = reverse('projects:project_detail', kwargs={'pk': project_cs.pk})
            response = self.client.get(detail_url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "ステータスを更新")
            self.assertNotContains(response, "契約書を取得")
            # The status text should also be visible
            self.assertContains(response, "先方確認中")

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
        mock_api_instance.send_document.assert_called_once_with(document_id=self.project.cloudsign_document_id)
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
        # Mock settings.LOG_DIR for testing log file path display
        self.mock_log_dir_patch = patch('projects.views.settings.LOG_DIR', new_callable=MagicMock)
        self.mock_log_dir = self.mock_log_dir_patch.start()
        self.mock_log_dir.__truediv__.return_value = '/mock/path/debug.log' # Simulate path
        self.mock_log_dir.exists.return_value = True

    def tearDown(self):
        self.mock_log_dir_patch.stop()

    @patch('os.path.exists', return_value=True)
    @patch('projects.views.open', new_callable=MagicMock) # Use MagicMock for open
    def test_log_view_displays_parsed_log_content(self, mock_open_file, mock_exists):
        """
        Tests that the view correctly displays parsed log content, distinguishing internal and API logs.
        """
        log_content = (
            "INFO 2023-10-27 12:34:56,789 projects.views projects.views 123 456 Internal Log Message\n"
            "ERROR 2023-10-27 12:34:57,890 projects.cloudsign_api projects.cloudsign_api 789 012 API Error Message.\n"
            "WARNING 2023-10-27 12:34:58,901 django.request django.request 111 222 Some Django warning."
        )
        mock_file_handle = MagicMock()
        mock_file_handle.__enter__.return_value.__iter__.return_value = log_content.splitlines()
        mock_open_file.return_value = mock_file_handle

        response = self.client.get(self.log_url) 
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/log_view.html')
        
        # Check for parsed log entries in context
        log_entries_context = response.context['log_entries']
        self.assertEqual(len(log_entries_context), 3)

        # The log entries are reversed in the view, so we check them in reverse order of the log file content.
        # Entry 1: Django Log (Warning)
        self.assertEqual(log_entries_context[0]['level'], "警告")
        self.assertEqual(log_entries_context[0]['logger_name'], "django.request")
        self.assertEqual(log_entries_context[0]['log_type'], "内部")
        
        # Entry 2: API Log (Error)
        self.assertEqual(log_entries_context[1]['level'], "エラー")
        self.assertEqual(log_entries_context[1]['logger_name'], "projects.cloudsign_api")
        self.assertEqual(log_entries_context[1]['message'], "API Error Message.")
        self.assertEqual(log_entries_context[1]['log_type'], "API")

        # Entry 3: Internal Log (Info)
        self.assertEqual(log_entries_context[2]['level'], "情報")
        self.assertEqual(log_entries_context[2]['datetime'], "2023-10-27 12:34:56")
        self.assertEqual(log_entries_context[2]['logger_name'], "projects.views")
        self.assertEqual(log_entries_context[2]['message'], "Internal Log Message")
        self.assertEqual(log_entries_context[2]['log_type'], "内部")

        mock_exists.assert_called_once()
        mock_open_file.assert_called_once_with(
            '/mock/path/debug.log', 'r', encoding='utf-8', errors='ignore'
        )

    @patch('os.path.exists', return_value=True)
    @patch('projects.views.open', new_callable=MagicMock)
    def test_log_view_parses_contextual_info(self, mock_open_file, mock_exists):
        """
        Tests that the view correctly parses and extracts contextual information 
        (operation, project_id) from enriched log messages.
        """
        log_content = (
            "ERROR 2023-10-28 10:00:00,000 projects.views projects.views 123 456 "
            "[ProjectManageView][save_and_send][Project: 42] Something went wrong."
        )
        mock_file_handle = MagicMock()
        mock_file_handle.__enter__.return_value.__iter__.return_value = log_content.splitlines()
        mock_open_file.return_value = mock_file_handle

        # Create a dummy project so the reverse URL lookup works
        Project.objects.create(id=42, title="Test Project 42")

        response = self.client.get(self.log_url)
        
        self.assertEqual(response.status_code, 200)
        
        log_entries = response.context.get('log_entries')
        self.assertIsNotNone(log_entries)
        self.assertEqual(len(log_entries), 1)
        
        entry = log_entries[0]
        self.assertEqual(entry.get('operation'), 'save_and_send')
        self.assertEqual(entry.get('project_id'), '42')
        self.assertEqual(entry.get('project_url'), reverse('projects:project_detail', kwargs={'pk': 42}))

    @patch('os.path.exists', return_value=False)
    def test_log_view_file_not_found(self, mock_exists):
        """
        Tests that the view handles a non-existent log file correctly.
        """
        response = self.client.get(self.log_url)
            
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/log_view.html')
        
        # Assert the view's context is correct
        self.assertFalse(response.context['log_file_exists'])
        self.assertEqual(len(response.context['log_entries']), 0)
        
        mock_exists.assert_called_once_with('/mock/path/debug.log')

class EmbeddedSigningViewTests(TestCase):
    def setUp(self):
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.client = Client()
        self.project = Project.objects.create(title="Test Project for Embedded Signing", cloudsign_document_id="doc_embed_123")
        self.participant = Participant.objects.create(
            project=self.project,
            name="Test Participant",
            email="test@example.com",
            cloudsign_participant_id="part_embed_456",
            recipient_id="rec_embed_789"
        )
        self.embedded_signing_url = reverse(
            'projects:embedded_signing_view',
            kwargs={'project_pk': self.project.pk, 'participant_pk': self.participant.pk}
        )
        self.detail_url = reverse('projects:project_detail', kwargs={'pk': self.project.pk})

    @patch('projects.views.CloudSignAPIClient')
    def test_embedded_signing_success(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.get_embedded_signing_url.return_value = {
            "url": "https://embedded.cloudsign.jp/signing/some_url_token",
            "expires_at": "2026-01-08T12:00:00Z"
        }

        response = self.client.get(self.embedded_signing_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/embedded_signing.html')
        self.assertIn('signing_url', response.context)
        self.assertEqual(response.context['signing_url'], "https://embedded.cloudsign.jp/signing/some_url_token")
        self.assertContains(response, "https://embedded.cloudsign.jp/signing/some_url_token")

        mock_api_instance.get_embedded_signing_url.assert_called_once_with(
            document_id=self.project.cloudsign_document_id,
            participant_id=self.participant.cloudsign_participant_id,
            recipient_id=self.participant.recipient_id
        )

    @patch('projects.views.CloudSignAPIClient')
    def test_embedded_signing_no_document_id(self, MockCloudSignAPIClient):
        self.project.cloudsign_document_id = ""
        self.project.save()

        response = self.client.get(self.embedded_signing_url, follow=True)
        self.assertRedirects(response, self.detail_url)
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "CloudSignドキュメントIDが設定されていません。")
        MockCloudSignAPIClient.return_value.get_embedded_signing_url.assert_not_called()

    @patch('projects.views.CloudSignAPIClient')
    def test_embedded_signing_no_cloudsign_participant_id(self, MockCloudSignAPIClient):
        self.participant.cloudsign_participant_id = ""
        self.participant.save()

        response = self.client.get(self.embedded_signing_url, follow=True)
        self.assertRedirects(response, self.detail_url)
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "CloudSignの参加者IDが設定されていません。")
        MockCloudSignAPIClient.return_value.get_embedded_signing_url.assert_not_called()

    @patch('projects.views.CloudSignAPIClient')
    def test_embedded_signing_api_error(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.get_embedded_signing_url.side_effect = requests.exceptions.RequestException("API Error")

        response = self.client.get(self.embedded_signing_url, follow=True)
        self.assertRedirects(response, self.detail_url)
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("組込み署名URLの取得に失敗しました", str(messages[0]))
        mock_api_instance.get_embedded_signing_url.assert_called_once()


class EmbeddedProjectCreateViewTests(TestCase):
    def setUp(self):
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.client = Client()
        self.create_url = reverse('projects:embedded_project_create_new') # New URL name
        self.success_url = reverse('projects:embedded_project_create_success') # New Success URL

    def test_get_create_view(self):
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/embedded_project_form.html') # New template name
        self.assertIn('project_form', response.context)
        self.assertIn('contract_file_formset', response.context)
        self.assertIn('participant_formset', response.context)
        self.assertContains(response, '組み込み署名案件作成')

    def test_post_create_draft_success(self):
        self.assertEqual(Project.objects.count(), 0)
        project_data = {
            'title': 'New Embedded Draft Project',
            'description': 'A draft description for embedded signing.',
            'participants-TOTAL_FORMS': '1',
            'participants-INITIAL_FORMS': '0',
            'participants-0-name': 'Draft Signer',
            'participants-0-email': 'draft@example.com',
            'participants-0-order': '0',
            'files-TOTAL_FORMS': '0',
            'files-INITIAL_FORMS': '0',
            'save_draft': ''
        }
        response = self.client.post(self.create_url, project_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        new_project = Project.objects.get(title='New Embedded Draft Project')
        self.assertIsNotNone(new_project)
        self.assertIsNone(new_project.cloudsign_document_id) # Should not have a CS document ID
        self.assertEqual(new_project.participants.count(), 1)
        messages = list(response.context['messages'])
        self.assertTrue(any("案件と関連データが下書きとして保存されました。" in str(m) for m in messages))
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': new_project.pk})) # Redirect to project detail

    @patch('projects.views.CloudSignAPIClient')
    def test_post_create_and_get_signing_urls_success(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.create_document.return_value = {'id': 'embedded_doc_id', 'title': 'Embedded Project'}
        mock_api_instance.get_document.return_value = {'id': 'embedded_doc_id', 'participants': [], 'files': []} # Used for existing checks
        mock_api_instance.add_participant.side_effect = ["embedded_part_id_1", "embedded_part_id_2"] # Simulate adding two participants
        mock_api_instance.add_file_to_document.return_value = {} # Mock return value
        mock_api_instance.get_embedded_signing_url.side_effect = [
            {'url': 'https://embedded.cloudsign.jp/signer1', 'expires_at': '2026-01-08T12:00:00Z'},
            {'url': 'https://embedded.cloudsign.jp/signer2', 'expires_at': '2026-01-08T12:00:00Z'}
        ]

        dummy_file = SimpleUploadedFile("embedded_doc.pdf", b"file content", content_type="application/pdf")
        
        project_data = {
            'title': 'New Embedded Project',
            'description': 'Description for embedded signing.',
            'participants-TOTAL_FORMS': '2',
            'participants-INITIAL_FORMS': '0',
            'participants-0-name': 'Signer One',
            'participants-0-email': 'signer1@example.com',
            'participants-0-order': '0',
            'participants-1-name': 'Signer Two',
            'participants-1-email': 'signer2@example.com',
            'participants-1-order': '1',
            'files-TOTAL_FORMS': '1',
            'files-INITIAL_FORMS': '0',
            'files-0-file': dummy_file,
            'get_signing_urls': '' # New button name
        }

        response = self.client.post(self.create_url, project_data, follow=True)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/embedded_project_success.html') # Redirects to success page
        
        new_project = Project.objects.get(title='New Embedded Project')
        self.assertEqual(new_project.cloudsign_document_id, 'embedded_doc_id')
        self.assertEqual(new_project.participants.count(), 2)
        self.assertEqual(new_project.participants.all()[0].cloudsign_participant_id, "embedded_part_id_1")
        self.assertEqual(new_project.participants.all()[1].cloudsign_participant_id, "embedded_part_id_2")

        mock_api_instance.create_document.assert_called_once_with('New Embedded Project')
        mock_api_instance.add_participant.call_count = 2 # Called for two participants
        mock_api_instance.add_file_to_document.assert_called_once()
        mock_api_instance.get_embedded_signing_url.call_count = 2 # Called for each participant

        context_signing_urls = response.context['signing_urls']
        self.assertEqual(len(context_signing_urls), 2)
        self.assertEqual(context_signing_urls[0]['name'], 'Signer One')
        self.assertEqual(context_signing_urls[0]['url'], 'https://embedded.cloudsign.jp/signer1')
        self.assertEqual(context_signing_urls[1]['name'], 'Signer Two')
        self.assertEqual(context_signing_urls[1]['url'], 'https://embedded.cloudsign.jp/signer2')

        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any("案件が作成され、組み込み署名URLが生成されました。" in str(m) for m in messages_list))

    @patch('projects.views.CloudSignAPIClient')
    def test_post_create_and_get_signing_urls_no_files(self, MockCloudSignAPIClient):
        project_data = {
            'title': 'Project without files',
            'participants-TOTAL_FORMS': '1',
            'participants-INITIAL_FORMS': '0',
            'participants-0-name': 'Test',
            'participants-0-email': 'test@test.com',
            'participants-0-order': '0',
            'files-TOTAL_FORMS': '1', # Formset has a form, but no file uploaded
            'files-INITIAL_FORMS': '0',
            'files-0-file': '', # Empty file field
            'get_signing_urls': ''
        }
        response = self.client.post(self.create_url, project_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/embedded_project_form.html')
        self.assertContains(response, "CloudSignドキュメント作成には、少なくとも1つのファイルが必要です。")
        MockCloudSignAPIClient.return_value.create_document.assert_not_called()

    @patch('projects.views.CloudSignAPIClient')
    def test_post_create_and_get_signing_urls_no_participants(self, MockCloudSignAPIClient):
        dummy_file = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")
        project_data = {
            'title': 'Project without participants',
            'participants-TOTAL_FORMS': '0',
            'participants-INITIAL_FORMS': '0',
            'files-TOTAL_FORMS': '1',
            'files-INITIAL_FORMS': '0',
            'files-0-file': dummy_file,
            'get_signing_urls': ''
        }
        response = self.client.post(self.create_url, project_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/embedded_project_form.html')
        self.assertContains(response, "CloudSignドキュメント作成には、少なくとも1人の宛先が必要です。")
        MockCloudSignAPIClient.return_value.create_document.assert_not_called()

    def test_post_no_embedded_signer_error(self):
        dummy_file = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")
        project_data = {
            'title': 'Project with no embedded signer',
            'participants-TOTAL_FORMS': '1',
            'participants-INITIAL_FORMS': '0',
            'participants-0-name': 'Normal Signer',
            'participants-0-email': 'normal@example.com',
            'participants-0-order': '1',
            'participants-0-is_embedded_signer': '', # Not checked
            'files-TOTAL_FORMS': '1',
            'files-INITIAL_FORMS': '0',
            'files-0-file': dummy_file,
            'create_and_get_urls': ''
        }
        response = self.client.post(self.create_url, project_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/embedded_project_form.html')
        self.assertContains(response, "少なくとも1人は「組み込み署名者」として指定する必要があります。")

    def test_post_embedded_signer_no_tel_error(self):
        dummy_file = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")
        project_data = {
            'title': 'Project with embedded signer no tel',
            'participants-TOTAL_FORMS': '1',
            'participants-INITIAL_FORMS': '0',
            'participants-0-name': 'Embedded Signer',
            'participants-0-email': 'embedded@example.com',
            'participants-0-order': '1',
            'participants-0-is_embedded_signer': 'on', # Checked
            'participants-0-tel': '', # Empty tel
            'files-TOTAL_FORMS': '1',
            'files-INITIAL_FORMS': '0',
            'files-0-file': dummy_file,
            'create_and_get_urls': ''
        }
        response = self.client.post(self.create_url, project_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/embedded_project_form.html')
        self.assertContains(response, "組み込み署名者には電話番号が必須です。")

    @patch('projects.views.CloudSignAPIClient')
    def test_post_api_error(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.create_embedded_signing_document.side_effect = Exception("Connection Timeout")

        dummy_file = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")
        project_data = {
            'title': 'API Error Project',
            'files-TOTAL_FORMS': '1',
            'files-INITIAL_FORMS': '0',
            'files-0-file': dummy_file,
            'participants-TOTAL_FORMS': '1',
            'participants-INITIAL_FORMS': '0',
            'participants-0-name': 'Embedded Signer',
            'participants-0-email': 'embedded@example.com',
            'participants-0-order': '1',
            'participants-0-is_embedded_signer': 'on',
            'participants-0-tel': '09011112222',
            'create_and_get_urls': ''
        }
        
        response = self.client.post(self.create_url, project_data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/embedded_project_form.html')
        self.assertContains(response, "CloudSign連携中にエラーが発生しました: Connection Timeout")
        self.assertEqual(Project.objects.count(), 0) # Verify project creation was rolled back


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

    def test_detail_view_button_visibility(self, MockCloudSignAPIClient):
        """
        Tests the visibility of 'Status Update' and 'Get Contract' buttons.
        """
        mock_api_instance = MockCloudSignAPIClient.return_value

        with self.subTest("Project without cloudsign_document_id"):
            project_no_cs = Project.objects.create(title="No CS ID")
            detail_url = reverse('projects:project_detail', kwargs={'pk': project_no_cs.pk})
            response = self.client.get(detail_url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "ステータスを更新")
            self.assertNotContains(response, "契約書を取得")

        with self.subTest("Project with CS ID and status 'Concluded'"):
            project_cs = Project.objects.create(title="With CS ID", cloudsign_document_id="doc_123")
            mock_api_instance.get_document.return_value = {
                "id": "doc_123",
                "status": 2,  # 締結済 (Corrected based on CloudSign API spec)
                "participants": []
            }
            detail_url = reverse('projects:project_detail', kwargs={'pk': project_cs.pk})
            response = self.client.get(detail_url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "ステータスを更新")
            self.assertContains(response, "契約書を取得")
            # The status text should also be visible
            self.assertContains(response, "締結済")

        with self.subTest("Project with CS ID and status not 'Concluded'"):
            # Re-use the same project, just change the mock return value
            mock_api_instance.get_document.return_value = {
                "id": "doc_123",
                "status": 1,  # 先方確認中
                "participants": []
            }
            detail_url = reverse('projects:project_detail', kwargs={'pk': project_cs.pk})
            response = self.client.get(detail_url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "ステータスを更新")
            self.assertNotContains(response, "契約書を取得")
            # The status text should also be visible
            self.assertContains(response, "先方確認中")

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
        mock_api_instance.send_document.assert_called_once_with(document_id=self.project.cloudsign_document_id)
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
        # Mock settings.LOG_DIR for testing log file path display
        self.mock_log_dir_patch = patch('projects.views.settings.LOG_DIR', new_callable=MagicMock)
        self.mock_log_dir = self.mock_log_dir_patch.start()
        self.mock_log_dir.__truediv__.return_value = '/mock/path/debug.log' # Simulate path
        self.mock_log_dir.exists.return_value = True

    def tearDown(self):
        self.mock_log_dir_patch.stop()

    @patch('os.path.exists', return_value=True)
    @patch('projects.views.open', new_callable=MagicMock) # Use MagicMock for open
    def test_log_view_displays_parsed_log_content(self, mock_open_file, mock_exists):
        """
        Tests that the view correctly displays parsed log content, distinguishing internal and API logs.
        """
        log_content = (
            "INFO 2023-10-27 12:34:56,789 projects.views projects.views 123 456 Internal Log Message\n"
            "ERROR 2023-10-27 12:34:57,890 projects.cloudsign_api projects.cloudsign_api 789 012 API Error Message.\n"
            "WARNING 2023-10-27 12:34:58,901 django.request django.request 111 222 Some Django warning."
        )
        mock_file_handle = MagicMock()
        mock_file_handle.__enter__.return_value.__iter__.return_value = log_content.splitlines()
        mock_open_file.return_value = mock_file_handle

        response = self.client.get(self.log_url) 
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/log_view.html')
        
        # Check for parsed log entries in context
        log_entries_context = response.context['log_entries']
        self.assertEqual(len(log_entries_context), 3)

        # The log entries are reversed in the view, so we check them in reverse order of the log file content.
        # Entry 1: Django Log (Warning)
        self.assertEqual(log_entries_context[0]['level'], "警告")
        self.assertEqual(log_entries_context[0]['logger_name'], "django.request")
        self.assertEqual(log_entries_context[0]['log_type'], "内部")
        
        # Entry 2: API Log (Error)
        self.assertEqual(log_entries_context[1]['level'], "エラー")
        self.assertEqual(log_entries_context[1]['logger_name'], "projects.cloudsign_api")
        self.assertEqual(log_entries_context[1]['message'], "API Error Message.")
        self.assertEqual(log_entries_context[1]['log_type'], "API")

        # Entry 3: Internal Log (Info)
        self.assertEqual(log_entries_context[2]['level'], "情報")
        self.assertEqual(log_entries_context[2]['datetime'], "2023-10-27 12:34:56")
        self.assertEqual(log_entries_context[2]['logger_name'], "projects.views")
        self.assertEqual(log_entries_context[2]['message'], "Internal Log Message")
        self.assertEqual(log_entries_context[2]['log_type'], "内部")

        mock_exists.assert_called_once()
        mock_open_file.assert_called_once_with(
            '/mock/path/debug.log', 'r', encoding='utf-8', errors='ignore'
        )

    @patch('os.path.exists', return_value=True)
    @patch('projects.views.open', new_callable=MagicMock)
    def test_log_view_parses_contextual_info(self, mock_open_file, mock_exists):
        """
        Tests that the view correctly parses and extracts contextual information 
        (operation, project_id) from enriched log messages.
        """
        log_content = (
            "ERROR 2023-10-28 10:00:00,000 projects.views projects.views 123 456 "
            "[ProjectManageView][save_and_send][Project: 42] Something went wrong."
        )
        mock_file_handle = MagicMock()
        mock_file_handle.__enter__.return_value.__iter__.return_value = log_content.splitlines()
        mock_open_file.return_value = mock_file_handle

        # Create a dummy project so the reverse URL lookup works
        Project.objects.create(id=42, title="Test Project 42")

        response = self.client.get(self.log_url)
        
        self.assertEqual(response.status_code, 200)
        
        log_entries = response.context.get('log_entries')
        self.assertIsNotNone(log_entries)
        self.assertEqual(len(log_entries), 1)
        
        entry = log_entries[0]
        self.assertEqual(entry.get('operation'), 'save_and_send')
        self.assertEqual(entry.get('project_id'), '42')
        self.assertEqual(entry.get('project_url'), reverse('projects:project_detail', kwargs={'pk': 42}))

    @patch('os.path.exists', return_value=False)
    def test_log_view_file_not_found(self, mock_exists):
        """
        Tests that the view handles a non-existent log file correctly.
        """
        response = self.client.get(self.log_url)
            
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/log_view.html')
        
        # Assert the view's context is correct
        self.assertFalse(response.context['log_file_exists'])
        self.assertEqual(len(response.context['log_entries']), 0)
        
        mock_exists.assert_called_once_with('/mock/path/debug.log')

class EmbeddedSigningViewTests(TestCase):
    def setUp(self):
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.client = Client()
        self.project = Project.objects.create(title="Test Project for Embedded Signing", cloudsign_document_id="doc_embed_123")
        self.participant = Participant.objects.create(
            project=self.project,
            name="Test Participant",
            email="test@example.com",
            cloudsign_participant_id="part_embed_456",
            recipient_id="rec_embed_789"
        )
        self.embedded_signing_url = reverse(
            'projects:embedded_signing_view',
            kwargs={'project_pk': self.project.pk, 'participant_pk': self.participant.pk}
        )
        self.detail_url = reverse('projects:project_detail', kwargs={'pk': self.project.pk})

    @patch('projects.views.CloudSignAPIClient')
    def test_embedded_signing_success(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.get_embedded_signing_url.return_value = {
            "url": "https://embedded.cloudsign.jp/signing/some_url_token",
            "expires_at": "2026-01-08T12:00:00Z"
        }

        response = self.client.get(self.embedded_signing_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/embedded_signing.html')
        self.assertIn('signing_url', response.context)
        self.assertEqual(response.context['signing_url'], "https://embedded.cloudsign.jp/signing/some_url_token")
        self.assertContains(response, "https://embedded.cloudsign.jp/signing/some_url_token")

        mock_api_instance.get_embedded_signing_url.assert_called_once_with(
            document_id=self.project.cloudsign_document_id,
            participant_id=self.participant.cloudsign_participant_id,
            recipient_id=self.participant.recipient_id
        )

    @patch('projects.views.CloudSignAPIClient')
    def test_embedded_signing_no_document_id(self, MockCloudSignAPIClient):
        self.project.cloudsign_document_id = ""
        self.project.save()

        response = self.client.get(self.embedded_signing_url, follow=True)
        self.assertRedirects(response, self.detail_url)
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "CloudSignドキュメントIDが設定されていません。")
        MockCloudSignAPIClient.return_value.get_embedded_signing_url.assert_not_called()

    @patch('projects.views.CloudSignAPIClient')
    def test_embedded_signing_no_cloudsign_participant_id(self, MockCloudSignAPIClient):
        self.participant.cloudsign_participant_id = ""
        self.participant.save()

        response = self.client.get(self.embedded_signing_url, follow=True)
        self.assertRedirects(response, self.detail_url)
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "CloudSignの参加者IDが設定されていません。")
        MockCloudSignAPIClient.return_value.get_embedded_signing_url.assert_not_called()

    @patch('projects.views.CloudSignAPIClient')
    def test_embedded_signing_api_error(self, MockCloudSignAPIClient):
        mock_api_instance = MockCloudSignAPIClient.return_value
        mock_api_instance.get_embedded_signing_url.side_effect = requests.exceptions.RequestException("API Error")

        response = self.client.get(self.embedded_signing_url, follow=True)
        self.assertRedirects(response, self.detail_url)
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("組込み署名URLの取得に失敗しました", str(messages[0]))
        mock_api_instance.get_embedded_signing_url.assert_called_once()
