from django.test import TestCase, Client
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import json

from projects.cloudsign_api import CloudSignAPIClient
from projects.models import CloudSignConfig, Project, ContractFile
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile # Add this import

class CloudSignAPIClientTests(TestCase):

    @patch('projects.models.CloudSignConfig.objects')
    def setUp(self, mock_cloudsign_config_objects):
        # Ensure CloudSignConfig is mocked before initializing the client
        mock_config = MagicMock()
        mock_config.client_id = "test_client_id"
        mock_config.api_base_url = "https://api-sandbox.cloudsign.jp"
        mock_cloudsign_config_objects.first.return_value = mock_config

        # Clear any existing singleton instance to ensure a fresh one for each test
        CloudSignAPIClient._instance = None
        self.client = CloudSignAPIClient()

        # Reset initialized state for each test if necessary for singleton
        self.client._initialized = False 
        self.client.__init__()

        # Ensure that the client_id and api_base_url are loaded from the mocked config
        self.assertEqual(self.client.client_id, "test_client_id")
        self.assertEqual(self.client.api_base_url, "https://api-sandbox.cloudsign.jp")

    @patch('requests.post')
    def test_get_access_token_success(self, mock_post):
        # Mock a successful response from the CloudSign API
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response

        # Call the _get_access_token method
        token = self.client._get_access_token()

        # Assertions
        self.assertEqual(token, "test_access_token")
        self.assertEqual(self.client.access_token, "test_access_token")
        self.assertIsNotNone(self.client.token_expires_at)
        
        # Verify requests.post was called with the correct URL and data
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
        # Set an expired token and a slightly in-the-future expiry for initial state
        self.client.access_token = "expired_token"
        self.client.token_expires_at = datetime.now() - timedelta(minutes=5)

        # Mock a successful response for the refresh
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response

        # Call the _get_access_token method
        token = self.client._get_access_token()

        # Assertions
        self.assertEqual(token, "new_access_token")
        self.assertEqual(self.client.access_token, "new_access_token")
        self.assertIsNotNone(self.client.token_expires_at)
        
        # Verify requests.post was called once to get a new token
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_get_access_token_cached(self, mock_post):
        # Set a valid, non-expired token
        self.client.access_token = "valid_token"
        self.client.token_expires_at = datetime.now() + timedelta(minutes=30)

        # Call the _get_access_token method
        token = self.client._get_access_token()

        # Assertions
        self.assertEqual(token, "valid_token")
        self.assertEqual(self.client.access_token, "valid_token")
        self.assertIsNotNone(self.client.token_expires_at)
        
        # Verify requests.post was NOT called because the token was cached
        mock_post.assert_not_called()

    @patch('requests.request')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_create_document_success(self, mock_get_access_token_method, mock_request):
        def _mock_get_access_token_side_effect():
            self.client.access_token = "dummy_access_token"
            self.client.token_expires_at = datetime.now() + timedelta(hours=1)
            return "dummy_access_token"
        mock_get_access_token_method.side_effect = _mock_get_access_token_side_effect

        # Mock requests.request for successful document creation
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "doc_id_123", "title": "Test Document"}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        # Create a mock file object
        mock_file = MagicMock()
        mock_file.name = 'test_file.pdf'
        mock_file.read.return_value = b'pdf_content'
        mock_file.seek.return_value = None

        title = "My Test Document"
        files = [mock_file]

        response_data = self.client.create_document(title, files=files)

        self.assertEqual(response_data, {"id": "doc_id_123", "title": "Test Document"})
        
        # Verify _make_authenticated_request called requests.request correctly
        mock_get_access_token_method.assert_called_once()
        mock_request.assert_called_once()
        
        call_args, call_kwargs = mock_request.call_args
        
        self.assertEqual(call_args[0], "POST")
        self.assertEqual(call_args[1], "https://api-sandbox.cloudsign.jp/documents")
        
        self.assertIn("headers", call_kwargs)
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer dummy_access_token")
        
        self.assertIn("data", call_kwargs)
        self.assertIn("files", call_kwargs)

        expected_data = {'data': json.dumps({'title': title})}
        self.assertEqual(call_kwargs['data'], expected_data)

        # Check file content
        uploaded_files = call_kwargs['files']
        self.assertEqual(len(uploaded_files), 1)
        file_part_name, (filename, file_content, content_type) = uploaded_files[0]
        self.assertEqual(file_part_name, 'files')
        self.assertEqual(filename, 'test_file.pdf')
        self.assertEqual(file_content, b'pdf_content')
        self.assertEqual(content_type, 'application/pdf')

    @patch('requests.request')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_get_document_success(self, mock_get_access_token_method, mock_request):
        def _mock_get_access_token_side_effect():
            self.client.access_token = "dummy_access_token"
            self.client.token_expires_at = datetime.now() + timedelta(hours=1)
            return "dummy_access_token"
        mock_get_access_token_method.side_effect = _mock_get_access_token_side_effect

        # Mock requests.request for successful document retrieval
        mock_response = MagicMock()
        mock_response.status_code = 200
        expected_document_data = {"id": "doc_id_123", "title": "Test Document", "status": 0}
        mock_response.json.return_value = expected_document_data
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        document_id = "doc_id_123"
        response_data = self.client.get_document(document_id)

        self.assertEqual(response_data, expected_document_data)
        
        mock_get_access_token_method.assert_called_once()
        mock_request.assert_called_once()
        
        call_args, call_kwargs = mock_request.call_args
        
        self.assertEqual(call_args[0], "GET")
        self.assertEqual(call_args[1], f"https://api-sandbox.cloudsign.jp/documents/{document_id}")
        
        self.assertIn("headers", call_kwargs)
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer dummy_access_token")

    @patch('requests.request')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_add_participant_success(self, mock_get_access_token_method, mock_request):
        def _mock_get_access_token_side_effect():
            self.client.access_token = "dummy_access_token"
            self.client.token_expires_at = datetime.now() + timedelta(hours=1)
            return "dummy_access_token"
        mock_get_access_token_method.side_effect = _mock_get_access_token_side_effect

        # Mock requests.request for successful participant addition
        mock_response = MagicMock()
        mock_response.status_code = 200
        expected_response_data = {"id": "doc_id_123", "participants": [{"email": "test@example.com", "name": "Test User"}]}
        mock_response.json.return_value = expected_response_data
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        document_id = "doc_id_123"
        email = "test@example.com"
        name = "Test User"

        response_data = self.client.add_participant(document_id, email, name)

        self.assertEqual(response_data, expected_response_data)
        
        mock_get_access_token_method.assert_called_once()
        mock_request.assert_called_once()
        
        call_args, call_kwargs = mock_request.call_args
        
        self.assertEqual(call_args[0], "POST")
        self.assertEqual(call_args[1], f"https://api-sandbox.cloudsign.jp/documents/{document_id}/participants")
        
        self.assertIn("headers", call_kwargs)
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer dummy_access_token")

        self.assertIn("data", call_kwargs)
        self.assertEqual(call_kwargs["data"], {"email": email, "name": name})

    @patch('requests.request')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_update_document_success(self, mock_get_access_token_method, mock_request):
        def _mock_get_access_token_side_effect():
            self.client.access_token = "dummy_access_token"
            self.client.token_expires_at = datetime.now() + timedelta(hours=1)
            return "dummy_access_token"
        mock_get_access_token_method.side_effect = _mock_get_access_token_side_effect

        # Mock requests.request for successful document update
        mock_response = MagicMock()
        mock_response.status_code = 200
        expected_response_data = {"id": "doc_id_123", "title": "Updated Title", "status": 0}
        mock_response.json.return_value = expected_response_data
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        document_id = "doc_id_123"
        update_data = {"title": "Updated Title", "note": "Some note"}

        response_data = self.client.update_document(document_id, update_data)

        self.assertEqual(response_data, expected_response_data)
        
        mock_get_access_token_method.assert_called_once()
        mock_request.assert_called_once()
        
        call_args, call_kwargs = mock_request.call_args
        
        self.assertEqual(call_args[0], "PUT")
        self.assertEqual(call_args[1], f"https://api-sandbox.cloudsign.jp/documents/{document_id}")
        
        self.assertIn("headers", call_kwargs)
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer dummy_access_token")

        self.assertIn("data", call_kwargs)
        self.assertEqual(call_kwargs["data"], update_data)



class ProjectUpdateViewTests(TestCase):
    def setUp(self):
        CloudSignAPIClient._instance = None # Ensure a fresh singleton instance
        # Create a CloudSignConfig instance for the client to load
        CloudSignConfig.objects.create(
            client_id="test_client_id",
            api_base_url="https://api-sandbox.cloudsign.jp"
        )
        # Create a Project instance with a cloudsign_document_id
        self.project = Project.objects.create(
            title="Initial Project Title",
            description="Initial Description",
            cloudsign_document_id="existing_cloudsign_doc_id"
        )
        self.update_url = reverse('projects:project_update', kwargs={'pk': self.project.pk})

    @patch('projects.cloudsign_api.CloudSignAPIClient.update_document')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    @patch('projects.views.ContractFileFormSet') # Mock the formset
    def test_update_document_called_on_project_update(self, mock_formset_class, mock_get_access_token, mock_update_document):
        # Ensure _get_access_token returns a dummy token
        mock_get_access_token.return_value = "dummy_access_token"

        # Mock the formset instance
        mock_formset_instance = MagicMock()
        mock_formset_instance.is_valid.return_value = True
        mock_formset_instance.save.return_value = None # Ensure save doesn't raise errors
        mock_formset_class.return_value = mock_formset_instance # When formset is instantiated, return our mock

        # Mock the update_document method to return a successful response
        mock_update_document.return_value = {"id": self.project.cloudsign_document_id, "title": "Updated Project Title"}

        updated_title = "Updated Project Title"
        updated_description = "Updated Description for Project"
        response = self.client.post(self.update_url, {
            'title': updated_title,
            'description': updated_description,
            # No need for form-TOTAL_FORMS etc. if formset is mocked
        })
        
        self.project.refresh_from_db()

        # Assert that update_document was called
        mock_update_document.assert_called_once_with(
            document_id=self.project.cloudsign_document_id,
            update_data={
                "title": updated_title,
                "note": updated_description,
            }
        )

        # Assert redirection to success_url
        self.assertRedirects(response, reverse('projects:project_list'))
        self.assertEqual(self.project.title, updated_title)
        self.assertEqual(self.project.description, updated_description)

class ProjectDetailViewTests(TestCase):
    def setUp(self):
        CloudSignAPIClient._instance = None # Ensure a fresh singleton instance
        # Create a CloudSignConfig instance for the client to load
        CloudSignConfig.objects.create(
            client_id="test_client_id",
            api_base_url="https://api-sandbox.cloudsign.jp"
        )
        self.client = Client()

    @patch('projects.cloudsign_api.CloudSignAPIClient.get_document')
    def test_project_detail_view_shows_participants(self, mock_get_document):
        # Create a Project instance with a cloudsign_document_id
        project = Project.objects.create(
            title="Project with Participants",
            description="Description",
            cloudsign_document_id="doc_id_with_participants"
        )
        detail_url = reverse('projects:project_detail', kwargs={'pk': project.pk})

        # Mock get_document for successful document retrieval with participants
        mock_get_document.return_value = {
            "id": "doc_id_with_participants",
            "status": "waiting",
            "participants": [
                {"email": "participant1@example.com", "name": "Participant One"},
                {"email": "participant2@example.com", "name": "Participant Two"}
            ]
        }

        response = self.client.get(detail_url)

        # Assertions
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
        # Ensure a fresh singleton instance of CloudSignAPIClient for each test
        CloudSignAPIClient._instance = None 

        # Create a CloudSignConfig instance for the client to load
        CloudSignConfig.objects.create(
            client_id="test_client_id",
            api_base_url="https://api-sandbox.cloudsign.jp"
        )
        # Create a Project instance with a cloudsign_document_id
        self.project = Project.objects.create(
            title="Test Project for Participant",
            description="Description",
            cloudsign_document_id="doc_id_for_participant_test"
        )
        self.client = Client()
        self.add_participant_url = reverse('projects:add_participant', kwargs={'pk': self.project.pk})

    def test_get_add_participant_form(self):
        # Ensure that the form is displayed correctly on GET request
        response = self.client.get(self.add_participant_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/participant_form.html')
        self.assertContains(response, '参加者メールアドレス')
        self.assertContains(response, '参加者名')

    @patch('projects.cloudsign_api.CloudSignAPIClient.add_participant')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_post_add_participant_success(self, mock_get_access_token, mock_add_participant):
        # Ensure _get_access_token returns a dummy token
        mock_get_access_token.return_value = "dummy_access_token"
        
        # Mock add_participant to return a successful response
        mock_add_participant.return_value = {"status": "success"}

        data = {
            'email': 'new_participant@example.com',
            'name': 'New Participant'
        }
        response = self.client.post(self.add_participant_url, data, follow=True)

        # Assert that add_participant was called with correct arguments
        mock_add_participant.assert_called_once_with(
            document_id=self.project.cloudsign_document_id,
            email=data['email'],
            name=data['name']
        )
        # Assert redirection to project detail page
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': self.project.pk}))
        # Check for success message
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), f"参加者 {data['name']} が正常に追加されました。")

    @patch('projects.cloudsign_api.CloudSignAPIClient.add_participant')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_post_add_participant_form_invalid(self, mock_get_access_token, mock_add_participant):
        # Ensure _get_access_token returns a dummy token
        mock_get_access_token.return_value = "dummy_access_token"

        # Try to submit with invalid data (e.g., missing email)
        data = {
            'email': '',  # Invalid email
            'name': 'Invalid User'
        }
        response = self.client.post(self.add_participant_url, data)

        # Assert that add_participant was NOT called
        mock_add_participant.assert_not_called()
        # Assert that form is re-rendered with errors
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/participant_form.html')
        self.assertFormError(response, 'form', 'email', ['This field is required.'])

    @patch('projects.cloudsign_api.CloudSignAPIClient.add_participant')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_post_add_participant_api_error(self, mock_get_access_token, mock_add_participant):
        # Ensure _get_access_token returns a dummy token
        mock_get_access_token.return_value = "dummy_access_token"

        # Mock add_participant to raise an exception
        mock_add_participant.side_effect = Exception("CloudSign API Error")

        data = {
            'email': 'error_user@example.com',
            'name': 'Error User'
        }
        response = self.client.post(self.add_participant_url, data)

        # Assert that add_participant was called
        mock_add_participant.assert_called_once()
        # Assert that form is re-rendered with errors and error message is shown
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/participant_form.html')
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("参加者の追加に失敗しました: CloudSign API Error", str(messages[0]))

    @patch('projects.cloudsign_api.CloudSignAPIClient.add_participant')
    @patch('projects.cloudsign_api.CloudSignAPIClient._get_access_token')
    def test_post_add_participant_no_cloudsign_document_id(self, mock_get_access_token, mock_add_participant):
        # Ensure _get_access_token returns a dummy token
        mock_get_access_token.return_value = "dummy_access_token"
        
        # Create a project without a cloudsign_document_id
        project_no_doc_id = Project.objects.create(
            title="Project No Doc ID",
            description="Description",
            cloudsign_document_id=""
        )
        add_participant_url_no_doc_id = reverse('projects:add_participant', kwargs={'pk': project_no_doc_id.pk})

        data = {
            'email': 'no_doc_id_user@example.com',
            'name': 'No Doc ID User'
        }
        response = self.client.post(add_participant_url_no_doc_id, data, follow=True)

        # Assert that add_participant was NOT called
        mock_add_participant.assert_not_called()
        # Assert redirection to project detail page
        self.assertRedirects(response, reverse('projects:project_detail', kwargs={'pk': project_no_doc_id.pk}))
        # Check for error message
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "CloudSignドキュメントIDがないため、参加者を追加できません。")

