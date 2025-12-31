from django.test import TestCase, Client
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, date
import json

from projects.cloudsign_api import CloudSignAPIClient
from projects.models import CloudSignConfig, Project, ContractFile
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

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

        expected_url = "https://api-sandbox.cloudsign.jp/oauth2/token"
        expected_headers = {"Content-Type": "application/json"}
        expected_json_data = {
            "grant_type": "client_credentials",
            "client_id": "test_client_id",
        }
        mock_post.assert_called_once_with(
            expected_url,
            headers=expected_headers,
            json=expected_json_data,
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


class ProjectUpdateViewTests(TestCase):
    def setUp(self):
        CloudSignAPIClient._instance = None
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.project = Project.objects.create(title="Initial Project Title", description="Initial Description", cloudsign_document_id="existing_cloudsign_doc_id")
        self.update_url = reverse('projects:project_update', kwargs={'pk': self.project.pk})
        self.client = Client()

    @patch('projects.cloudsign_api.CloudSignAPIClient.update_document')
    @patch('projects.views.ContractFileFormSet')
    def test_update_document_called_on_project_update(self, mock_formset_class, mock_update_document):
        mock_formset_instance = MagicMock()
        mock_formset_instance.is_valid.return_value = True
        mock_formset_class.return_value = mock_formset_instance

        mock_update_document.return_value = {"id": self.project.cloudsign_document_id, "title": "Updated Project Title"}

        updated_title = "Updated Project Title"
        updated_description = "Updated Description for Project"
        response = self.client.post(self.update_url, {
            'title': updated_title,
            'description': updated_description,
        })
        
        self.project.refresh_from_db()

        mock_update_document.assert_called_once_with(
            document_id=self.project.cloudsign_document_id,
            update_data={"title": updated_title, "note": updated_description}
        )
        self.assertRedirects(response, reverse('projects:project_list'))
        self.assertEqual(self.project.title, updated_title)
        self.assertEqual(self.project.description, updated_description)

class ProjectDetailViewTests(TestCase):
    def setUp(self):
        CloudSignAPIClient._instance = None
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.client = Client()

    @patch('projects.cloudsign_api.CloudSignAPIClient.get_document')
    def test_project_detail_view_shows_participants(self, mock_get_document):
        project = Project.objects.create(title="Project with Participants", description="Description", cloudsign_document_id="doc_id_with_participants")
        detail_url = reverse('projects:project_detail', kwargs={'pk': project.pk})

        mock_get_document.return_value = {
            "id": "doc_id_with_participants",
            "status": "waiting",
            "participants": [
                {"email": "participant1@example.com", "name": "Participant One"},
                {"email": "participant2@example.com", "name": "Participant Two"}
            ]
        }

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/project_detail.html')
        self.assertIn('cloudsign_participants', response.context)
        self.assertEqual(len(response.context['cloudsign_participants']), 2)
        self.assertEqual(response.context['cloudsign_participants'][0]['name'], "Participant One")
        self.assertContains(response, "Participant One (participant1@example.com)")
        self.assertContains(response, "Participant Two (participant2@example.com)")
        mock_get_document.assert_called_once_with(project.cloudsign_document_id)

class ParticipantCreateViewTests(TestCase):
    def setUp(self):
        CloudSignAPIClient._instance = None 
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.project = Project.objects.create(title="Test Project for Participant", description="Description", cloudsign_document_id="doc_id_for_participant_test")
        self.client = Client()
        self.add_participant_url = reverse('projects:add_participant', kwargs={'pk': self.project.pk})

    def test_get_add_participant_form(self):
        response = self.client.get(self.add_participant_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/participant_form.html')
        self.assertContains(response, '参加者メールアドレス')
        self.assertContains(response, '参加者名')

    @patch('projects.cloudsign_api.CloudSignAPIClient.add_participant')
    def test_post_add_participant_success(self, mock_add_participant):
        mock_add_participant.return_value = {"status": "success"}

        data = {'email': 'new_participant@example.com', 'name': 'New Participant'}
        response = self.client.post(self.add_participant_url, data, follow=True)

        mock_add_participant.assert_called_once_with(document_id=self.project.cloudsign_document_id, email=data['email'], name=data['name'])
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': self.project.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), f"参加者 {data['name']} が正常に追加されました。")

    @patch('projects.cloudsign_api.CloudSignAPIClient.add_participant')
    def test_post_add_participant_form_invalid(self, mock_add_participant):
        data = {'email': '', 'name': 'Invalid User'}
        response = self.client.post(self.add_participant_url, data)
        mock_add_participant.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/participant_form.html')
        self.assertFormError(response, 'form', 'email', ['This field is required.'])

    @patch('projects.cloudsign_api.CloudSignAPIClient.add_participant')
    def test_post_add_participant_api_error(self, mock_add_participant):
        mock_add_participant.side_effect = Exception("CloudSign API Error")
        data = {'email': 'error_user@example.com', 'name': 'Error User'}
        response = self.client.post(self.add_participant_url, data)
        mock_add_participant.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/participant_form.html')
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("参加者の追加に失敗しました: 予期せぬエラー: CloudSign API Error", str(messages[0]))

    @patch('projects.cloudsign_api.CloudSignAPIClient.add_participant')
    def test_post_add_participant_no_cloudsign_document_id(self, mock_add_participant):
        project_no_doc_id = Project.objects.create(title="Project No Doc ID", description="Description", cloudsign_document_id="")
        add_participant_url_no_doc_id = reverse('projects:add_participant', kwargs={'pk': project_no_doc_id.pk})
        data = {'email': 'no_doc_id_user@example.com', 'name': 'No Doc ID User'}
        response = self.client.post(add_participant_url_no_doc_id, data, follow=True)
        mock_add_participant.assert_not_called()
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': project_no_doc_id.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "CloudSignドキュメントIDがないため、参加者を追加できません。")

class DocumentSendViewTests(TestCase):
    def setUp(self):
        CloudSignAPIClient._instance = None
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.project = Project.objects.create(title="Project for Sending", description="Description for send test", cloudsign_document_id="doc_id_for_send_test")
        self.client = Client()
        self.send_document_url = reverse('projects:send_document', kwargs={'pk': self.project.pk})

    @patch('projects.cloudsign_api.CloudSignAPIClient.send_document')
    def test_post_send_document_success(self, mock_send_document):
        mock_send_document.return_value = {"status": "sent"}
        response = self.client.post(self.send_document_url, follow=True)
        mock_send_document.assert_called_once_with(document_id=self.project.cloudsign_document_id, send_data={})
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': self.project.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), f"CloudSignドキュメント (ID: {self.project.cloudsign_document_id}) が正常に送信されました。")

    @patch('projects.cloudsign_api.CloudSignAPIClient.send_document')
    def test_post_send_document_api_error(self, mock_send_document):
        mock_send_document.side_effect = Exception("API Send Error")
        response = self.client.post(self.send_document_url, follow=True)
        mock_send_document.assert_called_once()
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': self.project.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("CloudSignドキュメントの送信に失敗しました: 予期せぬエラー: API Send Error", str(messages[0]))

    @patch('projects.cloudsign_api.CloudSignAPIClient.send_document')
    def test_post_send_document_no_cloudsign_document_id(self, mock_send_document):
        project_no_doc_id = Project.objects.create(title="Project No Doc ID for Send", description="Description", cloudsign_document_id="")
        send_document_url_no_doc_id = reverse('projects:send_document', kwargs={'pk': project_no_doc_id.pk})
        response = self.client.post(send_document_url_no_doc_id, follow=True)
        mock_send_document.assert_not_called()
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': project_no_doc_id.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "CloudSignドキュメントIDがないため、ドキュメントを送信できません。")


class DocumentDownloadViewTests(TestCase):
    def setUp(self):
        CloudSignAPIClient._instance = None
        CloudSignConfig.objects.create(client_id="test_client_id", api_base_url="https://api-sandbox.cloudsign.jp")
        self.project = Project.objects.create(title="Project for Download", description="Description for download test", cloudsign_document_id="doc_id_for_download_test")
        self.client = Client()
        self.download_document_url = reverse('projects:download_document', kwargs={'pk': self.project.pk})

    @patch('projects.cloudsign_api.CloudSignAPIClient.download_document')
    def test_get_download_document_success(self, mock_download_document):
        mock_download_document.return_value = b"This is a test PDF content."
        response = self.client.get(self.download_document_url)
        mock_download_document.assert_called_once_with(self.project.cloudsign_document_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(f'attachment; filename="cloudsign_document_{self.project.cloudsign_document_id}.pdf"', response['Content-Disposition'])
        self.assertEqual(response.content, b"This is a test PDF content.")

    @patch('projects.cloudsign_api.CloudSignAPIClient.download_document')
    def test_get_download_document_api_error(self, mock_download_document):
        mock_download_document.side_effect = Exception("API Download Error")
        response = self.client.get(self.download_document_url, follow=True)
        mock_download_document.assert_called_once()
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': self.project.pk}))
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("CloudSignドキュメントのダウンロードに失敗しました: 予期せぬエラー: API Download Error", str(messages[0]))

    @patch('projects.cloudsign_api.CloudSignAPIClient.download_document')
    def test_get_download_document_no_cloudsign_document_id(self, mock_download_document):
        project_no_doc_id = Project.objects.create(title="Project No Doc ID for Download", description="Description", cloudsign_document_id="")
        download_document_url_no_doc_id = reverse('projects:download_document', kwargs={'pk': project_no_doc_id.pk})
        response = self.client.get(download_document_url_no_doc_id, follow=True)
        mock_download_document.assert_not_called()
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
    