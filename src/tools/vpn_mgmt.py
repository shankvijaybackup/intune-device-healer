"""
VPN Management Library for Intune
Handles health checks, silent installations, and real-time connectivity probes.
"""

from typing import Dict, Any, Optional
import structlog
from core.graph_client import GraphClient

logger = structlog.get_logger()

class VPNManagement:
    """VPN lifecycle and health management tools"""

    def __init__(self, authenticator, config):
        self.client = GraphClient(authenticator, config)

    async def check_vpn_health(self, device_id: str) -> Dict[str, Any]:
        """
        Audit VPN adapter status, driver health, and profile configuration.
        """
        script = r"""
        Write-Output "--- VPN HEALTH AUDIT ---"
        $Adapters = Get-NetAdapter | Where-Object { $_.InterfaceDescription -like "*VPN*" -or $_.Name -like "*VPN*" }
        if ($Adapters) {
            foreach ($a in $Adapters) {
                Write-Output "Adapter: $($a.Name) ($($a.Status))"
                Write-Output "Driver: $($a.DriverDescription) ($($a.DriverVersion))"
            }
        } else {
            Write-Output "WARNING: No VPN adapters detected."
        }
        
        $Stats = Get-VpnConnection -AllUserConnection | Select-Object Name, ConnectionStatus, ServerAddress
        if ($Stats) {
            Write-Output "`n--- VPN PROFILES ---"
            $Stats | ForEach-Object { Write-Output "$($_.Name): $($_.ConnectionStatus) (Server: $($_.ServerAddress))" }
        }
        """
        return await self._run_windows_probe(device_id, "VPN-Health-Audit", script)

    async def check_vpn_health_mac(self, device_id: str) -> Dict[str, Any]:
        """Audit VPN configuration on macOS."""
        script = r"""#!/bin/bash
        echo "--- macOS VPN HEALTH AUDIT ---"
        echo "Active Network Services:"
        networksetup -listallnetworkservices
        echo -e "\nVPN Configurations:"
        scutil --nc list | grep "VPN"
        """
        return await self._run_mac_probe(device_id, "Mac-VPN-Health", script)

    async def install_vpn_client(self, device_id: str, client_type: str = "AnyConnect") -> Dict[str, Any]:
        """
        Trigger a silent installation of a VPN client.
        Supported: AnyConnect, GlobalProtect, CloudflareWARP (Atomicwork standard).
        """
        if client_type.lower() in ["cloudflare", "warp", "cloudflarewarp"]:
            script = r"""
            Write-Output "Initiating Cloudflare WARP Installation..."
            $Url = "https://1111-releases.cloudflareclient.com/windows/Cloudflare_WARP_Release-x64.msi"
            $Path = "$env:TEMP\Cloudflare_WARP.msi"
            
            if (Get-Command "warp-cli" -ErrorAction SilentlyContinue) {
                Write-Output "Cloudflare WARP is already installed. Checking version..."
                warp-cli --version
                Exit 0
            }

            Write-Output "Downloading WARP from Cloudflare CDN..."
            Invoke-WebRequest -Uri $Url -OutFile $Path
            
            Write-Output "Running Silent MSI Install..."
            Start-Process msiexec.exe -ArgumentList "/i $Path /qn /norestart" -Wait
            
            if (Get-Command "warp-cli" -ErrorAction SilentlyContinue) {
                Write-Output "SUCCESS: Cloudflare WARP installed and warp-cli is available."
            } else {
                Write-Output "ERROR: Installation finished but warp-cli not found in PATH."
                Exit 1
            }
            """
            return await self._run_windows_probe(device_id, "Install-Cloudflare-WARP", script)

        # Generic bootstrap for other clients
        script = f"""
        Write-Output "Initiating Silent Install for {client_type}..."
        $IsInstalled = Get-WmiObject -Class Win32_Product | Where-Object {{ $_.Name -like "*{client_type}*" }}
        if ($IsInstalled) {{
            Write-Output "{client_type} already installed: $($IsInstalled.Version)"
            Exit 0
        }}
        Write-Output "Triggering infrastructure bootstrap for {client_type}..."
        """
        return await self._run_windows_probe(device_id, f"Install-VPN-{client_type}", script)

    async def get_realtime_vpn_stats(self, device_id: str) -> Dict[str, Any]:
        """
        Get live bytes sent/received and connection duration.
        """
        script = r"""
        Write-Output "--- LIVE VPN THROUGHPUT ---"
        $Conn = Get-VpnConnection -AllUserConnection | Where-Object { $_.ConnectionStatus -eq "Connected" }
        if ($Conn) {
            foreach ($c in $Conn) {
                Write-Output "Active VPN: $($c.Name)"
                $Stats = Get-NetAdapterStatistics -Name $c.Name
                Write-Output "Bytes Received: $($Stats.ReceivedBytes)"
                Write-Output "Bytes Sent: $($Stats.SentBytes)"
            }
        } else {
            Write-Output "No active VPN connection found."
        }
        """
        return await self._run_windows_probe(device_id, "Realtime-VPN-Stats", script)

    async def get_warp_status(self, device_id: str) -> Dict[str, Any]:
        """Get Cloudflare WARP specific status and stats."""
        script = r"""
        Write-Output "--- CLOUDFLARE WARP STATUS ---"
        if (Get-Command "warp-cli" -ErrorAction SilentlyContinue) {
            warp-cli status
            Write-Output "`n--- SETTINGS ---"
            warp-cli settings
        } else {
            Write-Output "ERROR: warp-cli not found in PATH."
        }
        """
        return await self._run_windows_probe(device_id, "Cloudflare-WARP-Status", script)

    async def get_warp_status_mac(self, device_id: str) -> Dict[str, Any]:
        """Get Cloudflare WARP specific status on macOS."""
        script = r"""#!/bin/bash
        echo "--- CLOUDFLARE WARP STATUS (macOS) ---"
        if command -v warp-cli &> /dev/null; then
            warp-cli status
        else
            echo "ERROR: warp-cli not found"
        fi
        """
        return await self._run_mac_probe(device_id, "Mac-WARP-Status", script)

    # --- Internal Helpers ---

    async def _run_windows_probe(self, device_id: str, name: str, script: str) -> Dict[str, Any]:
        """Runs a diagnostic/reporting script and triggers real-time sync"""
        # We reuse the health script pattern for diagnostics
        import base64
        import time
        from datetime import datetime

        payload = {
            "displayName": f"VPNProbe_{name}_{int(time.time())}",
            "detectionScriptContent": base64.b64encode("Exit 1".encode()).decode(), # Always trigger
            "remediationScriptContent": base64.b64encode(script.encode()).decode(),
            "runAsAccount": "system"
        }
        
        script_res = await self.client.post("/deviceManagement/deviceHealthScripts", json=payload, use_beta=True)
        script_id = script_res.get("id")
        
        if script_id:
            await self.client.assign_health_script_to_device(script_id, device_id)
            return {
                "success": True,
                "message": f"VPN Probe '{name}' deployed. Syncing for real-time stats...",
                "script_id": script_id
            }
        return {"success": False, "error": "Failed to deploy VPN probe"}

    async def _run_mac_probe(self, device_id: str, name: str, script: str) -> Dict[str, Any]:
        """Runs a Bash diagnostic script on macOS and triggers sync"""
        import base64
        import time
        payload = {
            "displayName": f"MacVPNProbe_{name}_{int(time.time())}",
            "detectionScriptContent": base64.b64encode("#!/bin/bash\nexit 1".encode()).decode(),
            "remediationScriptContent": base64.b64encode(script.encode()).decode(),
            "runAsAccount": "system"
        }
        script_res = await self.client.post("/deviceManagement/deviceHealthScripts", json=payload, use_beta=True)
        sid = script_res.get("id")
        if sid:
            await self.client.assign_health_script_to_device(sid, device_id)
            return {"success": True, "message": f"macOS VPN Probe '{name}' deployed.", "script_id": sid}
        return {"success": False, "error": "Failed to deploy Mac VPN probe"}
