"""
M365 Management Tools
"""

from typing import Optional, Dict, Any, List
import structlog
from tools.universal_api import UniversalApiTools

logger = structlog.get_logger()

class M365MgmtTools:
    """Tools for managing M365 users, groups, and entities"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.api = UniversalApiTools(authenticator, config)

    async def list_users(self, filter: Optional[str] = None, select: Optional[str] = None, top: int = 100) -> Dict[str, Any]:
        """List users in the tenant"""
        params = {"$top": str(top)}
        if filter: params["$filter"] = filter
        if select: params["$select"] = select
        
        return await self.api.call_microsoft_api("graph", "users", query_params=params)

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get detailed information for a specific user"""
        return await self.api.call_microsoft_api("graph", f"users/{user_id}")

    async def list_groups(self, filter: Optional[str] = None, top: int = 100) -> Dict[str, Any]:
        """List groups in the tenant"""
        params = {"$top": str(top)}
        if filter: params["$filter"] = filter
        
        return await self.api.call_microsoft_api("graph", "groups", query_params=params)

    async def get_group_members(self, group_id: str) -> Dict[str, Any]:
        """Get members of a group"""
        return await self.api.call_microsoft_api("graph", f"groups/{group_id}/members")

    async def manage_group_membership(self, group_id: str, member_id: str, action: str = "add") -> Dict[str, Any]:
        """Add or remove a member from a group"""
        if action == "add":
            body = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{member_id}"}
            return await self.api.call_microsoft_api("graph", f"groups/{group_id}/members/$ref", method="POST", body=body)
        else:
            return await self.api.call_microsoft_api("graph", f"groups/{group_id}/members/{member_id}/$ref", method="DELETE")

    async def list_applications(self, filter: Optional[str] = None) -> Dict[str, Any]:
        """List application registrations"""
        params = {}
        if filter: params["$filter"] = filter
        return await self.api.call_microsoft_api("graph", "applications", query_params=params)

    async def get_user_sign_ins(self, user_id: str, days: int = 7) -> Dict[str, Any]:
        """Get sign-in logs for a user"""
        # Note: requires AuditLog.Read.All and potentially specific licenses
        from datetime import datetime, timedelta
        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        filter = f"userPrincipalName eq '{user_id}' and createdDateTime ge {start_date}"
        return await self.api.call_microsoft_api("graph", "auditLogs/signIns", query_params={"$filter": filter})

    async def get_user_mfa_status(self, user_id: str) -> Dict[str, Any]:
        """Get MFA registration status for a user"""
        return await self.api.call_microsoft_api("graph", f"users/{user_id}/authentication/methods")
