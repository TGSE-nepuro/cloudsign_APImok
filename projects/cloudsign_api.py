import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from .models import CloudSignConfig
import logging

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
            self._initialized = True
            self._load_config()

    def _load_config(self):
        try:
            config = CloudSignConfig.objects.first()
            if not config:
                raise ImproperlyConfigured("CloudSignConfig is not set up. Please configure it in the admin panel.")
            self.client_id = config.client_id
            self.api_base_url = config.api_base_url
            logger.info(f"CloudSignAPIClient initialized with client_id: {self.client_id}, API Base URL: {self.api_base_url}")
        except Exception as e:
            logger.error(f"Failed to load CloudSignConfig: {e}")
            raise ImproperlyConfigured(f"Failed to load CloudSignConfig: {e}")

    def _get_access_token(self):
        # CloudSign API documentation is needed for the exact token endpoint and parameters.
        # Assuming a client credentials flow where client_id is exchanged for a token.
        # This is a placeholder implementation.
        if self.access_token:
            # TODO: Check if token is expired before returning
            return self.access_token

        token_url = f"{self.api_base_url}/oauth2/token" # This might be different, check docs
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            # "client_secret": settings.CLOUDSIGN_CLIENT_SECRET, # As per instructions, client_secret is not needed
        }

        try:
            response = requests.post(token_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            if not self.access_token:
                raise Exception("Access token not found in response.")
            logger.info("Successfully obtained CloudSign access token.")
            return self.access_token
        except requests.exceptions.RequestException as e:
            logger.error(f"Error obtaining CloudSign access token: {e}")
            raise Exception(f"Failed to obtain CloudSign access token: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during token acquisition: {e}")
            raise Exception(f"Unexpected error during token acquisition: {e}")

    def _make_authenticated_request(self, method, endpoint, **kwargs):
        if not self.access_token:
            self._get_access_token()

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        
        url = f"{self.api_base_url}{endpoint}"

        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during CloudSign API request to {endpoint}: {e.response.status_code} - {e.response.text}")
            # Attempt to refresh token if 401 Unauthorized
            if e.response.status_code == 401:
                logger.info("Access token expired or invalid, attempting to refresh.")
                self.access_token = None # Invalidate current token
                self._get_access_token() # Get new token
                headers["Authorization"] = f"Bearer {self.access_token}" # Update header
                response = requests.request(method, url, headers=headers, **kwargs) # Retry request
                response.raise_for_status()
                return response.json()
            raise Exception(f"CloudSign API request failed: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during CloudSign API request to {endpoint}: {e}")
            raise Exception(f"CloudSign API request failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during CloudSign API request to {endpoint}: {e}")
            raise Exception(f"Unexpected error during CloudSign API request to {endpoint}: {e}")

    # Example API methods (to be implemented based on actual needs)
    def create_document(self, document_data):
        # Placeholder for creating a document
        return self._make_authenticated_request("POST", "/v2/documents", json=document_data)

    def get_document_status(self, document_id):
        # Placeholder for getting document status
        return self._make_authenticated_request("GET", f"/v2/documents/{document_id}")

    def send_document(self, document_id, send_data):
        # Placeholder for sending a document
        return self._make_authenticated_request("POST", f"/v2/documents/{document_id}/send", json=send_data)
