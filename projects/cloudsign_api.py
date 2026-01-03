import requests
import logging
import json
from datetime import datetime, timedelta

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

    def create_document(self, title, files=None):
        """
        Creates a new document in CloudSign with a given title and attached files.
        Files are sent using multipart/form-data.
        :param title: The title of the document.
        :param files: A list of file-like objects (e.g., SimpleUploadedFile) to upload.
        :return: The API response containing document details.
        """
        data = {'data': json.dumps({'title': title})}
        
        files_to_upload = []
        if files:
            for f in files:
                f.seek(0) # Ensure file pointer is at the beginning
                # The key for the file part should be 'files' as per CloudSign API
                files_to_upload.append(('files', (f.name, f.read(), 'application/pdf')))
        
        return self._make_authenticated_request("POST", "/documents", data=data, files=files_to_upload)

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

    def add_participant(self, document_id, email, name):
        """
        Adds a participant to a CloudSign document.
        :param document_id: The ID of the document.
        :param email: The email address of the participant.
        :param name: The name of the participant.
        :return: The API response.
        """
        data = {
            "email": email,
            "name": name,
        }
        return self._make_authenticated_request("POST", f"/documents/{document_id}/participants", data=data)

    def update_document(self, document_id, update_data):
        """
        Updates the information of a CloudSign document.
        :param document_id: The ID of the document.
        :param update_data: A dictionary containing the data to update (e.g., {"title": "New Title"}).
        :return: The API response.
        """
        return self._make_authenticated_request("PUT", f"/documents/{document_id}", data=update_data)

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