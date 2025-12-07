import requests
import logging
import json
from datetime import datetime, timedelta

from django.core.exceptions import ImproperlyConfigured
from .models import CloudSignConfig

logger = logging.getLogger(__name__)

class CloudSignAPIClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.client_id = None
            self.api_base_url = None
            self.access_token = None
            self.token_expires_at = None
            self._initialized = True
            self._load_config()

    def _load_config(self):
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
        Obtains a new access token from CloudSign API.
        Manages token expiration.
        """
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.access_token

        token_url = f"{self.api_base_url}/oauth2/token"
        headers = {"Content-Type": "application/json"}
        json_data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
        }

        try:
            response = requests.post(token_url, headers=headers, json=json_data, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
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
        Handles token acquisition and refresh.
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
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during CloudSign API request to {endpoint}: {e.response.status_code} - {e.response.text}")
            if e.response.status_code == 401:
                logger.info("Access token may be expired. Refreshing and retrying.")
                self.access_token = None
                self.token_expires_at = None
                
                self._get_access_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                
                response = do_request()
                response.raise_for_status()
                if response.status_code == 204:
                    return None
                return response.json()
            raise Exception(f"CloudSign API request failed with status {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during CloudSign API request to {endpoint}: {e}")
            raise Exception(f"CloudSign API request failed due to a network error: {e}")

    def create_document(self, title, files=None):
        """
        Creates a document with files using multipart/form-data.
        :param title: The title of the document.
        :param files: A list of file-like objects to upload.
        :return: The API response.
        """
        data = {'data': json.dumps({'title': title})}
        
        files_to_upload = []
        if files:
            for f in files:
                f.seek(0)
                # The key for the file part should be 'files'
                files_to_upload.append(('files', (f.name, f.read(), 'application/pdf')))
        
        # Pass 'data' and 'files' kwargs to the generic request method
        return self._make_authenticated_request("POST", "/documents", data=data, files=files_to_upload)

    def get_document_status(self, document_id):
        """
        Gets the status of a document.
        """
        return self._make_authenticated_request("GET", f"/documents/{document_id}")

    def send_document(self, document_id, send_data):
        """
        Sends a document.
        `send_data` should be a dictionary, e.g., {"participants": [...]}
        """
        return self._make_authenticated_request("POST", f"/documents/{document_id}/send", json=send_data)
