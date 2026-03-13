"""
Remediation Library for Intune Managed Devices
Contains industry-standard detection and remediation scripts.
"""

from typing import Optional, Dict, Any, List
import structlog
from core.graph_client import GraphClient

logger = structlog.get_logger()

class RemediationLibrary:
    """Library of proactive remediations for Windows and macOS"""

    def __init__(self, authenticator, config):
        self.client = GraphClient(authenticator, config)

    # --- Windows Remediations ---

    async def deploy_disk_cleanup(self, device_id: str) -> Dict[str, Any]:
        """Deploy a remediation to clear temp files and notify user"""
        detection = """
        $Disk = Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='C:'"
        $FreeGB = $Disk.FreeSpace / 1GB
        if ($FreeGB -lt 10) { Write-Output "Low Disk: $FreeGB GB"; Exit 1 }
        Exit 0
        """
        remediation = """
        Write-Output "Starting Disk Cleanup..."
        Cleanmgr.exe /sagerun:1
        Get-ChildItem -Path "C:\\Windows\\Temp\\*" -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Output "Cleanup Complete."
        """
        return await self._create_and_assign_remediation(
            "Cleanup Disk Space", 
            detection, 
            remediation, 
            device_id
        )

    async def deploy_printer_spooler_fix(self, device_id: str) -> Dict[str, Any]:
        """Fix for stalled print jobs"""
        detection = """
        $Status = Get-Service -Name Spooler
        if ($Status.Status -ne 'Running') { Exit 1 }
        Exit 0
        """
        remediation = """
        Stop-Service -Name Spooler -Force
        $Files = Get-ChildItem -Path "C:\\Windows\\System32\\spool\\PRINTERS\\*"
        foreach ($File in $Files) { Remove-Item $File.FullName -Force }
        Start-Service -Name Spooler
        """
        return await self._create_and_assign_remediation(
            "Fix Printer Spooler", 
            detection, 
            remediation, 
            device_id
        )

    async def deploy_high_uptime_reboot(self, device_id: str) -> Dict[str, Any]:
        """Prompt user to reboot if uptime > 7 days"""
        detection = """
        $Uptime = (Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
        if ($Uptime.Days -ge 7) { Write-Output "High Uptime: $($Uptime.Days) days"; Exit 1 }
        Exit 0
        """
        remediation = """
        # Trigger a reboot prompt or force reboot
        Restart-Computer -Force -Confirm:$false
        """
        return await self._create_and_assign_remediation(
            "High Uptime Reboot", 
            detection, 
            remediation, 
            device_id
        )

    # --- Internal Helpers ---

    async def _create_and_assign_remediation(
        self, 
        name: str, 
        detection: str, 
        remediation: str, 
        device_id: str
    ) -> Dict[str, Any]:
        """Helper to create and assign a remediation script"""
        import base64
        
        # Create the script object
        payload = {
            "displayName": f"AutoHeal_{name}_{int(__import__('time').time())}",
            "detectionScriptContent": base64.b64encode(detection.encode()).decode(),
            "remediationScriptContent": base64.b64encode(remediation.encode()).decode(),
            "runAsAccount": "system"
        }
        
        # 1. Create the remediation
        script = await self.client.post("/deviceManagement/deviceHealthScripts", json=payload, use_beta=True)
        script_id = script.get("id")
        
        if not script_id:
            return {"success": False, "error": "Failed to create remediation script"}
            
        # 2. Assign to device
        # The GraphClient.assign_health_script_to_device handles the assignment AND the real-time sync
        assignment = await self.client.assign_health_script_to_device(script_id, device_id)
        
        return {
            "success": True,
            "script_id": script_id,
            "assignment": assignment,
            "message": f"Remediation '{name}' deployed and Real-Time Sync triggered."
        }
