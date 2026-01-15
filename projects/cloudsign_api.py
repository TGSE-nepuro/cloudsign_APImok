import requests
import logging
import json
from datetime import datetime, timedelta
import os # 追加
import re # 追加

from django.core.exceptions import ImproperlyConfigured
from .models import CloudSignConfig

logger = logging.getLogger(__name__)

class CloudSignAPIClient:
    """
    Singleton API client for interacting with the CloudSign API.
    Handles access token management (obtaining and refreshing) and
    authenticated requests.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Ensures only one instance of the client exists.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the client, loading configuration from the database.
        """
        if not hasattr(self, '_initialized'):
            self.client_id = None
            self.api_base_url = None
            self.access_token = None
            self.token_expires_at = None
            self._initialized = True
            self._load_config()

    def _load_config(self):
        """
        Loads CloudSign API configuration (client ID, base URL) from the database.
        Raises ImproperlyConfigured if the configuration is not found.
        """
        try:
            config = CloudSignConfig.objects.first()
            if not config:
                raise ImproperlyConfigured("CloudSignConfig is not set up. Please configure it in the admin panel.")
            self.client_id = config.client_id
            self.api_base_url = config.api_base_url.rstrip('/')
            logger.info(f"CloudSignAPIClient initialized with client_id: {self.client_id}, API Base URL: {self.api_base_url}")
        except Exception as e:
            logger.error(f"Failed to load CloudSignConfig: {e}")
            raise ImproperlyConfigured(f"Failed to load CloudSignConfig: {e}")

    def _get_access_token(self):
        """
        Obtains a new access token from CloudSign API if the current one is expired or missing.
        Manages token expiration internally.
        """
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.access_token

        token_url = f"{self.api_base_url}/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_id": self.client_id,
        }

        try:
            response = requests.post(token_url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
            # Set expiration a bit before actual expiry to ensure fresh token
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

            if not self.access_token:
                raise Exception("Access token not found in response.")
            
            logger.info("Successfully obtained CloudSign access token.")
            return self.access_token
        except requests.exceptions.RequestException as e:
            logger.error(f"Error obtaining CloudSign access token: {e}")
            raise Exception(f"Failed to obtain CloudSign access token: {e}")

    def _make_authenticated_request(self, method, endpoint, **kwargs):
        """
        Makes an authenticated request to the CloudSign API.
        Handles token acquisition and refresh, and retries on 401 errors.
        Can handle both JSON and multipart/form-data requests.
        """
        self._get_access_token()

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        
        url = f"{self.api_base_url}{endpoint}"

        def do_request():
            # The timeout is increased to 60 seconds to accommodate potentially large file uploads.
            return requests.request(method, url, headers=headers, timeout=60, **kwargs)

        try:
            response = do_request()
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            if response.status_code == 204: # No Content
                return None
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during CloudSign API request to {endpoint}: {e.response.status_code} - {e.response.text}")
            if e.response.status_code == 401:
                logger.info("Access token may be expired. Refreshing and retrying.")
                self.access_token = None
                self.token_expires_at = None
                
                # Retry request with a new token
                self._get_access_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                
                response = do_request()
                response.raise_for_status()
                if response.status_code == 204:
                    return None
                return response.json()
            raise # Re-raise other HTTP errors
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during CloudSign API request to {endpoint}: {e}")
            raise # Re-raise network errors

    def create_document(self, title):
        """
        Creates a new document in CloudSign with a given title.
        Files and parties are added in separate subsequent steps.
        :param title: The title of the document.
        :return: The API response containing document details (including document ID).
        """
        document_data = {
            'title': title,
            'send_to_parties': False, # Always create as draft first
        }

        return self._make_authenticated_request("POST", "/documents", data=document_data)

    def get_document(self, document_id):
        """
        Retrieves the details of a specific CloudSign document.
        :param document_id: The ID of the document.
        :return: The API response containing document details, including status and participants.
        """
        return self._make_authenticated_request("GET", f"/documents/{document_id}")

    def send_document(self, document_id):
        """
        Sends a CloudSign document, initiating the signing process.
        :param document_id: The ID of the document to send.
        :param send_data: A dictionary containing data for sending (e.g., {"participants": [...]}).
                          Can be empty if participants are already set and no other options are needed.
        :return: The API response.
        """
        return self._make_authenticated_request("POST", f"/documents/{document_id}")

    def add_participant(self, document_id, email, name, tel=None, callback=False, recipient_id=None):
        """
        Adds a participant to a CloudSign document.
        :param document_id: The ID of the document.
        :param email: The email address of the participant.
        :param name: The name of the participant.
        :param tel: Optional phone number for embedded signing (SMS authentication).
        :param callback: Boolean flag indicating if participant is for embedded signing (SMS authentication).
        :param recipient_id: Optional recipient_id for embedded signing (simple authentication).
        :return: The CloudSign participant ID of the newly added participant.
        """
        data = {
            "email": email,
            "name": name,
        }
        if tel:
            data['tel'] = tel
        if callback:
            data['callback'] = True
        if recipient_id:
            data['recipient_id'] = recipient_id
        
        # Ensure callback and recipient_id are not used together for the same participant if the API forbids it
        # Based on spec, recipient_id is for "簡易認証", callback/tel for "SMS認証". Assume mutual exclusivity if both set.
        if callback and recipient_id:
            logger.warning(f"Both 'callback' and 'recipient_id' were provided for participant {email}. 'recipient_id' will be ignored for SMS authentication.")
            del data['recipient_id'] # Prioritize SMS authentication as per our requirement.

        response_data = self._make_authenticated_request("POST", f"/documents/{document_id}/participants", data=data)
        
        # Find the newly added participant's ID in the response
        new_participant_id = None
        for participant in response_data.get('participants', []):
            if participant.get('email') == email and participant.get('name') == name:
                new_participant_id = participant.get('id')
                break
        
        if not new_participant_id:
            raise Exception(f"Could not find the ID of the newly added participant ({email}, {name}) in CloudSign response.")

        return new_participant_id

    def create_embedded_signing_document(self, title, files, participants_data):
        """
        Handles the full workflow for creating a document with embedded signing.
        1. Creates the document.
        2. Adds files to the document.
        3. Adds participants (distinguishing embedded signers).
        4. Generates embedded signing URLs for designated embedded signers.
        :param title: The title of the document.
        :param files: A list of file-like objects (e.g., SimpleUploadedFile) to upload.
        :param participants_data: A list of dictionaries, each containing participant details
                                  (e.g., {'name': '...', 'email': '...', 'tel': '...', 'is_embedded_signer': True}).
        :return: A tuple (document_id, list_of_signing_urls_info).
                 list_of_signing_urls_info is a list of dicts: {'name': '...', 'url': '...', 'expires_at': '...'}.
        """
        # 1. Create Document
        document_response = self.create_document(title)
        document_id = document_response['id']
        logger.info(f"[create_embedded_signing_document][create_document][Project: {document_id}] Document created successfully with ID: {document_id}")

        # 2. Add Files
        if not files:
            raise ValueError("No files provided for document creation.")
        for file in files:
            self.add_file_to_document(document_id, file)
            logger.info(f"[create_embedded_signing_document][add_file_to_document][Project: {document_id}] File '{file.name}' added.")
        
        # Store CloudSign participant IDs and their tel for generating signing URLs later
        embedded_signers_for_url_generation = []
        all_participants_with_cs_id = []

        # 3. Add Participants
        for participant_data in participants_data:
            name = participant_data['name']
            email = participant_data['email']
            is_embedded_signer = participant_data.get('is_embedded_signer', False)
            tel = participant_data.get('tel')
            recipient_id = participant_data.get('recipient_id') # For simple embedded auth if needed
            
            # Decide whether to use callback/tel or recipient_id based on is_embedded_signer
            if is_embedded_signer:
                if not tel:
                    raise ValueError(f"Phone number (tel) is required for embedded signer {name} ({email}).")
                cloudsign_participant_id = self.add_participant(
                    document_id, email, name, tel=tel, callback=True
                )
                embedded_signers_for_url_generation.append({
                    'name': name,
                    'cloudsign_participant_id': cloudsign_participant_id,
                    'tel': tel # Store tel for generating signing URL if needed
                })
                logger.info(f"[create_embedded_signing_document][add_participant][Project: {document_id}] Embedded signer '{name}' added with ID: {cloudsign_participant_id}")
            else:
                cloudsign_participant_id = self.add_participant(
                    document_id, email, name, recipient_id=recipient_id
                )
                logger.info(f"[create_embedded_signing_document][add_participant][Project: {document_id}] Participant '{name}' added with ID: {cloudsign_participant_id}")
            
            all_participants_with_cs_id.append({
                'name': name,
                'email': email,
                'cloudsign_participant_id': cloudsign_participant_id,
                'is_embedded_signer': is_embedded_signer
            })

        # 4. Generate Embedded Signing URLs for designated embedded signers
        generated_signing_urls_info = []
        for signer_info in embedded_signers_for_url_generation:
            signing_info = self.get_embedded_signing_url(
                document_id,
                signer_info['cloudsign_participant_id'],
                # recipient_id はSMS認証では不要
            )
            generated_signing_urls_info.append({
                'name': signer_info['name'],
                'url': signing_info['url'],
                'expires_at': signing_info['expires_at']
            })
            logger.info(f"[create_embedded_signing_document][get_embedded_signing_url][Project: {document_id}] Signing URL generated for '{signer_info['name']}'.")

        return document_id, generated_signing_urls_info, all_participants_with_cs_id

    def add_file_to_document(self, document_id, file):
        """
        Adds a PDF file to an existing CloudSign document.
        :param document_id: The ID of the document to add the file to.
        :param file: A file-like object (e.g., SimpleUploadedFile) to upload.
        :return: The API response.
        """
        files_to_upload = []
        file.seek(0) # Ensure file pointer is at the beginning
        
        # Use the file object's name directly, ensuring it ends with .pdf
        original_file_name = file.name
        base_name_without_ext, ext = os.path.splitext(os.path.basename(original_file_name))
        
        # Ensure the filename for the API has a .pdf extension
        if not ext or ext.lower() != '.pdf':
            # If no extension or wrong extension, append .pdf to the base name
            file_name_for_api = f"{base_name_without_ext}.pdf"
        else:
            file_name_for_api = original_file_name

        logger.info(f"Original file name: '{original_file_name}', File name for API: '{file_name_for_api}'")

        data_fields = {
            'name': file_name_for_api,
        }
        files_fields = {
            'uploadfile': (file_name_for_api, file.read(), 'application/pdf'),
        }

        # _make_authenticated_request の引数を変更
        response_data = self._make_authenticated_request(
            "POST", 
            f"/documents/{document_id}/files", 
            data=data_fields,   # 'name'フィールドを送る
            files=files_fields  # 'uploadfile'フィールドを送る
        )

        # --- ここに新しいログを追加 ---
        logger.debug(f"Response from add_file_to_document for doc_id={document_id}, file='{sanitized_file_name}': {response_data}")
        # --- ここまで新しいログを追加 ---

        return response_data

    def update_document(self, document_id, update_data):
        """
        Updates the information of a CloudSign document.
        :param document_id: The ID of the document.
        :param update_data: A dictionary containing the data to update (e.g., {"title": "New Title"}).
        :return: The API response.
        """
        return self._make_authenticated_request("PUT", f"/documents/{document_id}", data=update_data)

    def add_widget(self, document_id, file_id, widget_type, page, x, y, email, width=None, height=None, text=None, required=True):
        """
        Adds a widget (e.g., signature, seal, text) to a specific file within a CloudSign document.
        :param document_id: The ID of the document.
        :param file_id: The ID of the file within the document to add the widget to.
        :param widget_type: The type of widget (e.g., 'seal', 'signature', 'text', 'date').
        :param page: The page number (0-indexed) where the widget should be placed.
        :param x: The X coordinate of the widget's position.
        :param y: The Y coordinate of the widget's position.
        :param email: The email of the participant assigned to this widget.
        :param width: Optional width of the widget.
        :param height: Optional height of the widget.
        :param text: Optional text for text widgets.
        :param required: Whether the widget is required.
        :return: The API response.
        """
        payload = {
            "type": widget_type,
            "page": page,
            "x": x,
            "y": y,
            "email": email,
            "required": required,
        }
        if width is not None:
            payload["width"] = width
        if height is not None:
            payload["height"] = height
        if text is not None:
            payload["text"] = text

        return self._make_authenticated_request(
            "POST",
            f"/documents/{document_id}/files/{file_id}/widgets",
            json=payload # Send as JSON body
        )

    def get_embedded_signing_url(self, document_id, participant_id, recipient_id=None):
        """
        Obtains the embedded signing URL for a specific participant in a document.
        :param document_id: The ID of the document.
        :param participant_id: The CloudSign participant ID.
        :param recipient_id: Optional recipient_id for embedded signing (simple authentication).
        :return: The API response containing the signing URL and its expiration.
        """
        endpoint = f"/documents/{document_id}/participants/{participant_id}/signing_url"
        
        data = {}
        if recipient_id:
            data['recipient_id'] = recipient_id
        
        # The API spec for this endpoint shows POST with application/x-www-form-urlencoded
        # and a requestBody with recipient_id.
        return self._make_authenticated_request("POST", endpoint, data=data)

    def download_document(self, document_id):
        """
        Downloads the raw content of a signed CloudSign document file.
        :param document_id: The ID of the document.
        :return: The raw content (bytes) of the document file.
        :raises Exception: If the download fails due to API errors or network issues.
        """
        self._get_access_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        # Assuming the endpoint for downloading the file is /documents/{documentID}/file
        url = f"{self.api_base_url}/documents/{document_id}/file"

        try:
            # Use stream=True for potentially large files, but return content directly here
            response = requests.get(url, headers=headers, stream=True, timeout=60)
            response.raise_for_status() # Raise an exception for HTTP errors
            return response.content # Return raw content bytes
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during CloudSign document download for {document_id}: {e.response.status_code} - {e.response.text}")
            if e.response.status_code == 401:
                logger.info("Access token may be expired. Retrying download with refreshed token.")
                self.access_token = None
                self.token_expires_at = None
                self._get_access_token() # Refresh token
                headers["Authorization"] = f"Bearer {self.access_token}" # Update header with new token
                response = requests.get(url, headers=headers, stream=True, timeout=60)
                response.raise_for_status()
                return response.content
            raise # Re-raise other HTTP errors
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during CloudSign document download for {document_id}: {e}")
            raise # Re-raise network errors