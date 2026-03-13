"""
Advanced Intune Management Tools
"""

from typing import Optional, Dict, Any, List
import structlog
from core.graph_client import GraphClient

logger = structlog.get_logger()

class IntuneMgmtTools:
    """Tools for deep Intune operations (BitLocker, Autopilot, Apps)"""

    def __init__(self, authenticator, config):
        self.client = GraphClient(authenticator, config)

    async def get_bitlocker_recovery_key(self, device_id: str) -> Dict[str, Any]:
        """Retrieve BitLocker recovery keys for a managed device"""
        # 1. List BitLocker recovery keys associated with the device
        # Path: /informationProtection/bitlocker/recoveryKeys
        # Filter by deviceName or look up via device ID mapping
        # For simplicity in MCP, we'll try to find keys associated with the device's Azure AD ID
        
        # Note: This requires high-privilege permissions (DeviceManagementConfiguration.Read.All or similar)
        endpoint = f"/informationProtection/bitlocker/recoveryKeys?$filter=deviceId eq '{device_id}'"
        return await self.client.get(endpoint)

    async def list_autopilot_devices(self) -> List[Dict[str, Any]]:
        """List all devices registered in Windows Autopilot"""
        return await self.client.get_paged_results("/deviceManagement/windowsAutopilotDeviceIdentities")

    async def sync_autopilot(self) -> Dict[str, Any]:
        """Trigger a sync between Intune and the Autopilot service"""
        return await self.client.post("/deviceManagement/windowsAutopilotDeviceIdentities/sync")

    async def list_mobile_apps(self, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """List managed apps (Windows, iOS, Android, macOS)"""
        endpoint = "/deviceAppManagement/mobileApps"
        if platform:
            # Simple filter for the platform string in the odata type
            endpoint += f"?$filter=contains(microsoft.graph.mobileApp/largeIcon/value, '{platform}')"
        return await self.client.get_paged_results(endpoint)

    async def get_device_hardware_inventory(self, device_id: str) -> Dict[str, Any]:
        """Get detailed hardware specifications for a device"""
        # The managedDevice object contains a nested hardwareInformation property
        device = await self.client.get(f"/deviceManagement/managedDevices/{device_id}")
        if "hardwareInformation" in device:
            return device["hardwareInformation"]
        return {"error": "Hardware information not available for this device type"}

    async def set_primary_user(self, device_id: str, user_id: str) -> Dict[str, Any]:
        """Change the primary user (affinity) for a device"""
        endpoint = f"/deviceManagement/managedDevices/{device_id}/users/$ref"
        # The user_id should be the directory object ID
        user_ref = f"{self.client.base_url}/users/{user_id}"
        payload = {"@odata.id": user_ref}
        return await self.client.post(endpoint, json=payload)

    async def list_device_categories(self) -> List[Dict[str, Any]]:
        """List all defined device categories in the tenant"""
        return await self.client.get_paged_results("/deviceManagement/deviceCategories")
