"""
Collaboration Tools for SharePoint and Teams
"""

from typing import Optional, Dict, Any, List
import structlog
from tools.universal_api import UniversalApiTools

logger = structlog.get_logger()

class CollaborationTools:
    """Tools for SharePoint and Teams integration"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.api = UniversalApiTools(authenticator, config)

    async def create_sharepoint_site(self, display_name: str, alias: str, description: str = "") -> Dict[str, Any]:
        """Provision a new SharePoint site (via M365 Group)"""
        # In M365, creating a 'unified' group creates a SharePoint site
        body = {
            "description": description,
            "displayName": display_name,
            "groupTypes": ["Unified"],
            "mailEnabled": True,
            "mailNickname": alias,
            "securityEnabled": False
        }
        return await self.api.call_microsoft_api("graph", "groups", method="POST", body=body)

    async def manage_teams_channel(self, team_id: str, channel_name: str, description: str = "", action: str = "create") -> Dict[str, Any]:
        """Create or list Teams channels"""
        path = f"teams/{team_id}/channels"
        if action == "create":
            body = {
                "displayName": channel_name,
                "description": description
            }
            return await self.api.call_microsoft_api("graph", path, method="POST", body=body)
        else:
            return await self.api.call_microsoft_api("graph", path)

    async def list_onedrive_files(self, user_id: str = "me") -> Dict[str, Any]:
        """List files in a user's OneDrive"""
        path = f"{user_id}/drive/root/children"
        return await self.api.call_microsoft_api("graph", path)
