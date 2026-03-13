"""
Microsoft Graph API Authentication
"""

import time
from typing import Optional
from azure.identity import ClientSecretCredential
import msal
import structlog

logger = structlog.get_logger()


class GraphAuthenticator:
    """Handles authentication with Microsoft Graph API"""

    def __init__(self, config):
        self.config = config
        self.tenant_id = config.azure_tenant_id
        self.client_id = config.azure_client_id
        self.client_secret = config.azure_client_secret

        self.msal_app = None

        self._token_cache = None
        self._token_expiry = 0

        # Scopes required for Graph API
        self.scopes = ["https://graph.microsoft.com/.default"]

        logger.info("GraphAuthenticator initialized", tenant_id=self.tenant_id)

    async def _ensure_app(self):
        """Ensure MSAL app is initialized with current config"""
        if self.msal_app and self.tenant_id == self.config.azure_tenant_id:
            return

        self.tenant_id = self.config.azure_tenant_id
        self.client_id = self.config.azure_client_id
        self.client_secret = self.config.azure_client_secret

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            logger.warning("Azure credentials incomplete - skipping MSAL initialization")
            return

        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.msal_app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=authority
        )
        logger.info("Graph MSAL app initialized", tenant_id=self.tenant_id)

    async def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Get access token for Microsoft Graph API.
        """
        await self._ensure_app()
        if not self.msal_app:
            raise Exception("Cannot acquire token: Azure credentials not configured in Dashboard")

        current_time = time.time()

        # Return cached token if still valid
        if not force_refresh and self._token_cache and current_time < self._token_expiry:
            return self._token_cache

        try:
            # Try to get token from cache first
            result = self.msal_app.acquire_token_silent(
                scopes=self.scopes,
                account=None
            )

            # If no cached token, acquire new one
            if not result:
                logger.info("Acquiring new access token")
                result = self.msal_app.acquire_token_for_client(scopes=self.scopes)

            if "access_token" in result:
                self._token_cache = result["access_token"]
                # Set expiry to 5 minutes before actual expiry for safety
                self._token_expiry = current_time + result.get("expires_in", 3600) - 300

                logger.info("Access token acquired successfully")
                return self._token_cache
            else:
                error = result.get("error", "unknown_error")
                error_description = result.get("error_description", "No description")
                logger.error("Token acquisition failed", error=error, description=error_description)
                raise Exception(f"Authentication failed: {error} - {error_description}")

        except Exception as e:
            logger.error("Authentication error", error=str(e))
            raise

    async def get_headers(self) -> dict:
        """
        Get HTTP headers with authentication token.

        Returns:
            Dictionary with Authorization header
        """
        token = await self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def is_authenticated(self) -> bool:
        """Check if we have a valid cached token"""
        return self._token_cache is not None and time.time() < self._token_expiry
