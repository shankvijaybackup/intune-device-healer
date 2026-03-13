"""
Remote Action Tools for Intune Managed Devices
"""

from typing import Optional, Dict, Any
import structlog
from core.graph_client import GraphClient

logger = structlog.get_logger()

class RemoteActionsTools:
    """Tools for executing standard Intune remote actions"""

    def __init__(self, authenticator, config):
        self.client = GraphClient(authenticator, config)

    async def reboot_device(self, device_id: str) -> Dict[str, Any]:
        """Restart a managed device remotely"""
        return await self.client.execute_device_action(device_id, "rebootDevice")

    async def lock_device(self, device_id: str) -> Dict[str, Any]:
        """Lock a managed device remotely (Windows, macOS, iOS, Android)"""
        return await self.client.execute_device_action(device_id, "lockDevice")

    async def retire_device(self, device_id: str) -> Dict[str, Any]:
        """Retire a device (removes company data, remains in Intune)"""
        return await self.client.execute_device_action(device_id, "retire")

    async def wipe_device(self, device_id: str, keep_enrollment: bool = False) -> Dict[str, Any]:
        """Wipe a device (factory reset)"""
        # payload for wipe: https://learn.microsoft.com/en-us/graph/api/intune-devices-manageddevice-wipe
        json_data = {"keepEnrollmentData": keep_enrollment, "keepUserData": False}
        return await self.client.execute_device_action(device_id, "wipe", json=json_data)

    async def quick_scan_defender(self, device_id: str) -> Dict[str, Any]:
        """Trigger a Microsoft Defender quick scan on a Windows device"""
        return await self.client.execute_device_action(device_id, "windowsDefenderScan", json={"quickScan": True})

    async def full_scan_defender(self, device_id: str) -> Dict[str, Any]:
        """Trigger a Microsoft Defender full scan on a Windows device"""
        return await self.client.execute_device_action(device_id, "windowsDefenderScan", json={"quickScan": False})

    async def sync_device(self, device_id: str) -> Dict[str, Any]:
        """Trigger a device check-in/sync"""
        return await self.client.sync_device(device_id)

    async def collect_diagnostics(self, device_id: str) -> Dict[str, Any]:
        """
        Trigger a remote diagnostics collection request.
        The device will zip up logs and upload them to Azure.
        """
        # The beta API expects a complex object for the request parameters
        payload = {
            "managedDeviceLogCollectionRequest": {
                "templateType": "all"
            }
        }
        return await self.client.execute_device_action(
            device_id, 
            "createDeviceLogCollectionRequest", 
            json=payload,
            use_beta=True
        )
