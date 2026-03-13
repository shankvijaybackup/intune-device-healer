"""
M365 Policy Management Tools
"""

import json
from typing import Optional, Dict, Any, List
import structlog
from tools.universal_api import UniversalApiTools

logger = structlog.get_logger()

class PolicyMgmtTools:
    """Tools for managing CA and Intune policies"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.api = UniversalApiTools(authenticator, config)

    async def list_conditional_access_policies(self) -> Dict[str, Any]:
        """List all Conditional Access policies"""
        return await self.api.call_microsoft_api("graph", "identity/conditionalAccess/policies")

    async def get_ca_policy_details(self, policy_id: str) -> Dict[str, Any]:
        """Get details for a specific CA policy"""
        return await self.api.call_microsoft_api("graph", f"identity/conditionalAccess/policies/{policy_id}")

    async def list_intune_compliance_policies(self) -> Dict[str, Any]:
        """List Intune device compliance policies"""
        return await self.api.call_microsoft_api("graph", "deviceManagement/deviceCompliancePolicies")

    async def list_intune_configuration_profiles(self) -> Dict[str, Any]:
        """List Intune device configuration profiles"""
        return await self.api.call_microsoft_api("graph", "deviceManagement/deviceConfigurationPolicies")

    async def manage_named_locations(self, action: str = "list", location_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Manage Conditional Access named locations"""
        path = "identity/conditionalAccess/namedLocations"
        if action == "list":
            return await self.api.call_microsoft_api("graph", path)
        elif action == "create":
            return await self.api.call_microsoft_api("graph", path, method="POST", body=location_data)
        elif action == "delete" and location_data and "id" in location_data:
            return await self.api.call_microsoft_api("graph", f"{path}/{location_data['id']}", method="DELETE")
        else:
            return {"success": False, "error": f"Unsupported action or missing ID for {action}"}

    async def backup_policies(self, policy_types: List[str] = ["all"]) -> Dict[str, Any]:
        """Backup M365 policies to a summary JSON"""
        results = {}
        
        types_to_backup = policy_types
        if "all" in policy_types:
            types_to_backup = ["ca", "compliance", "configuration"]

        if "ca" in types_to_backup:
            ca = await self.list_conditional_access_policies()
            results["conditional_access"] = ca.get("data", {}).get("value", []) if ca.get("success") else []

        if "compliance" in types_to_backup:
            comp = await self.list_intune_compliance_policies()
            results["device_compliance"] = comp.get("data", {}).get("value", []) if comp.get("success") else []

        if "configuration" in types_to_backup:
            conf = await self.list_intune_configuration_profiles()
            results["device_configuration"] = conf.get("data", {}).get("value", []) if conf.get("success") else []

        return {
            "success": True, 
            "backup_summary": {
                "ca_count": len(results.get("conditional_access", [])),
                "compliance_count": len(results.get("device_compliance", [])),
                "configuration_count": len(results.get("device_configuration", [])),
            },
            "data": results
        }
