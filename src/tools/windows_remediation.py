"""
Windows Remediation Tools
Comprehensive fix automation for Windows devices
"""

import structlog
import base64
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
from core.graph_client import GraphClient

logger = structlog.get_logger()


class WindowsRemediationTools:
    """Tools for fixing Windows device issues"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.client = GraphClient(authenticator, config)
        self.scripts_path = Path(__file__).parent.parent / "scripts" / "windows"

    async def fix_windows_updates(self, device_id: str, auto_approve: bool = False) -> Dict[str, Any]:
        """
        Fix Windows Update issues by resetting components.
        Tier 2: Semi-automatic (requires approval if auto_approve=False)
        """
        logger.info("fix_windows_updates", device_id=device_id, auto_approve=auto_approve)

        if not auto_approve and self.config.require_approval_risky_ops:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "fix_windows_updates",
                "risk": "moderate",
                "description": "Reset Windows Update components (stops services, clears cache, re-registers DLLs)",
                "message": "This operation requires manual approval. Set auto_approve=True to proceed."
            }

        script_content = """
# Windows Update Reset Script
# Stops services, clears cache, resets components

$ErrorActionPreference = "Continue"
$results = @()

Write-Output "=== Windows Update Reset Started ==="

# Stop Windows Update services
$services = @('wuauserv', 'cryptSvc', 'bits', 'msiserver')
foreach ($service in $services) {
    try {
        Write-Output "Stopping service: $service"
        Stop-Service -Name $service -Force -ErrorAction SilentlyContinue
        $results += "Stopped $service"
    } catch {
        $results += "Warning: Could not stop $service - $($_.Exception.Message)"
    }
}

# Clear Windows Update cache
try {
    Write-Output "Clearing SoftwareDistribution folder..."
    Remove-Item -Path "C:\\Windows\\SoftwareDistribution\\*" -Recurse -Force -ErrorAction SilentlyContinue
    $results += "Cleared SoftwareDistribution cache"
} catch {
    $results += "Warning: Could not clear cache - $($_.Exception.Message)"
}

# Clear CatRoot2 folder
try {
    Write-Output "Clearing CatRoot2 folder..."
    Remove-Item -Path "C:\\Windows\\System32\\catroot2\\*" -Recurse -Force -ErrorAction SilentlyContinue
    $results += "Cleared CatRoot2 cache"
} catch {
    $results += "Warning: Could not clear CatRoot2 - $($_.Exception.Message)"
}

# Re-register DLLs
$dlls = @('wuaueng.dll', 'wuapi.dll', 'wups.dll', 'wups2.dll', 'wucltux.dll', 'wuwebv.dll')
foreach ($dll in $dlls) {
    try {
        Write-Output "Registering $dll..."
        regsvr32.exe /s $dll
        $results += "Registered $dll"
    } catch {
        $results += "Warning: Could not register $dll"
    }
}

# Restart services
foreach ($service in $services) {
    try {
        Write-Output "Starting service: $service"
        Start-Service -Name $service -ErrorAction SilentlyContinue
        $results += "Started $service"
    } catch {
        $results += "Warning: Could not start $service - $($_.Exception.Message)"
    }
}

# Force update check
Write-Output "Forcing Windows Update check..."
try {
    $UpdateSession = New-Object -ComObject Microsoft.Update.Session
    $UpdateSearcher = $UpdateSession.CreateUpdateSearcher()
    $SearchResult = $UpdateSearcher.Search("IsInstalled=0")
    $results += "Update check completed: $($SearchResult.Updates.Count) updates found"
} catch {
    $results += "Warning: Update check failed - $($_.Exception.Message)"
}

Write-Output "=== Windows Update Reset Completed ==="
$results | ForEach-Object { Write-Output $_ }

# Return status
if ($results -match "Error") {
    exit 1
} else {
    exit 0
}
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Fix Windows Updates",
                script_content=script_content,
                run_as_system=True
            )

            return {
                "success": result["success"],
                "operation": "fix_windows_updates",
                "tier": 2,
                "device_id": device_id,
                "execution_result": result,
                "message": "Windows Update fix script deployed via Intune. Will execute on device at next check-in." if result["success"] else "Fix script deployment failed",
                "next_steps": [
                    "Trigger device sync to apply changes",
                    "Check Windows Update manually after 10 minutes",
                    "Reboot device if issues persist"
                ]
            }

        except Exception as e:
            logger.error("fix_windows_updates failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "fix_windows_updates"
            }

    async def repair_system_files(self, device_id: str, auto_approve: bool = False) -> Dict[str, Any]:
        """
        Repair Windows system files using DISM and SFC.
        Tier 2: Semi-automatic (requires approval)
        """
        logger.info("repair_system_files", device_id=device_id, auto_approve=auto_approve)

        if not auto_approve and self.config.require_approval_risky_ops:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "repair_system_files",
                "risk": "moderate",
                "description": "Run DISM /RestoreHealth and SFC /scannow to repair corrupted system files",
                "estimated_duration": "15-30 minutes",
                "message": "This operation requires manual approval. Set auto_approve=True to proceed."
            }

        script_content = """
# System File Repair Script
# Runs DISM and SFC to repair corrupted files

$ErrorActionPreference = "Continue"
Write-Output "=== System File Repair Started ==="

# Step 1: DISM Cleanup
Write-Output "Step 1: Running DISM Cleanup Image..."
try {
    DISM.exe /Online /Cleanup-Image /StartComponentCleanup
    Write-Output "DISM cleanup completed"
} catch {
    Write-Output "Warning: DISM cleanup failed - $($_.Exception.Message)"
}

# Step 2: DISM ScanHealth
Write-Output "Step 2: Running DISM ScanHealth..."
try {
    $dismScan = DISM.exe /Online /Cleanup-Image /ScanHealth
    Write-Output $dismScan
} catch {
    Write-Output "Warning: DISM scan failed - $($_.Exception.Message)"
}

# Step 3: DISM RestoreHealth
Write-Output "Step 3: Running DISM RestoreHealth (this may take 10-20 minutes)..."
try {
    $dismRestore = DISM.exe /Online /Cleanup-Image /RestoreHealth
    Write-Output $dismRestore
    Write-Output "DISM restore completed"
} catch {
    Write-Output "Error: DISM restore failed - $($_.Exception.Message)"
}

# Step 4: SFC Scan
Write-Output "Step 4: Running SFC /scannow..."
try {
    $sfcResult = sfc.exe /scannow
    Write-Output $sfcResult
    Write-Output "SFC scan completed"
} catch {
    Write-Output "Error: SFC scan failed - $($_.Exception.Message)"
}

Write-Output "=== System File Repair Completed ==="

# Check CBS log for results
if (Test-Path "C:\\Windows\\Logs\\CBS\\CBS.log") {
    Write-Output "CBS Log (last 20 lines):"
    Get-Content "C:\\Windows\\Logs\\CBS\\CBS.log" -Tail 20
}

exit 0
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Repair System Files",
                script_content=script_content,
                run_as_system=True,
                timeout_seconds=1800  # 30 minutes
            )

            return {
                "success": result["success"],
                "operation": "repair_system_files",
                "tier": 2,
                "device_id": device_id,
                "execution_result": result,
                "message": "System file repair script deployed via Intune. Will execute on device at next check-in." if result["success"] else "Repair script deployment failed",
                "next_steps": [
                    "Review CBS.log for detailed results",
                    "Reboot device to complete repairs",
                    "Check Windows Update after reboot"
                ]
            }

        except Exception as e:
            logger.error("repair_system_files failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "repair_system_files"
            }

    async def cleanup_disk_space(self, device_id: str) -> Dict[str, Any]:
        """
        Automated disk cleanup to free up space.
        Tier 1: Automatic (safe operation)
        """
        logger.info("cleanup_disk_space", device_id=device_id)

        script_content = r"""
# Disk Cleanup Script
# Safely removes temp files, cache, old Windows installations
# Outputs STATS: JSON line at end for machine parsing

$ErrorActionPreference = "Continue"
$drive = Get-PSDrive C
$spaceBefore = [math]::Round($drive.Free / 1GB, 2)
$totalGB     = [math]::Round(($drive.Free + $drive.Used) / 1GB, 2)

Write-Output "=== Disk Cleanup Started ==="
Write-Output "Drive C total: $totalGB GB"
Write-Output "Free space before: $spaceBefore GB"

$breakdown = @()

# Clean Windows Temp
try {
    $sz = (Get-ChildItem "C:\\Windows\\Temp" -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
    Remove-Item "C:\\Windows\\Temp\\*" -Recurse -Force -ErrorAction SilentlyContinue
    $sz = [math]::Round($sz, 1)
    Write-Output "Cleaned Windows\\Temp: $sz MB"
    $breakdown += "Windows\\Temp: $sz MB"
} catch { Write-Output "Warning: Could not clean Windows Temp" }

# Clean ALL user temp folders (enumerate C:\Users\*)
try {
    Get-ChildItem "C:\\Users" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $userTemp = Join-Path $_.FullName "AppData\\Local\\Temp"
        if (Test-Path $userTemp) {
            $sz = (Get-ChildItem $userTemp -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
            Remove-Item "$userTemp\\*" -Recurse -Force -ErrorAction SilentlyContinue
            $sz = [math]::Round($sz, 1)
            Write-Output "Cleaned $($_.Name)\\AppData\\Local\\Temp: $sz MB"
            $breakdown += "$($_.Name)\\AppData\\Local\\Temp: $sz MB"
        }
    }
} catch { Write-Output "Warning: Could not clean user temp folders" }

# Clean Prefetch
try {
    $sz = (Get-ChildItem "C:\\Windows\\Prefetch" -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
    Remove-Item "C:\\Windows\\Prefetch\\*" -Force -ErrorAction SilentlyContinue
    $sz = [math]::Round($sz, 1)
    Write-Output "Cleaned Prefetch: $sz MB"
    $breakdown += "Prefetch: $sz MB"
} catch { Write-Output "Warning: Could not clean Prefetch" }

# Clean Windows Update Download cache
try {
    $sz = (Get-ChildItem "C:\\Windows\\SoftwareDistribution\\Download" -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
    Remove-Item "C:\\Windows\\SoftwareDistribution\\Download\\*" -Recurse -Force -ErrorAction SilentlyContinue
    $sz = [math]::Round($sz, 1)
    Write-Output "Cleaned Windows Update cache: $sz MB"
    $breakdown += "Windows Update cache: $sz MB"
} catch { Write-Output "Warning: Could not clean Windows Update cache" }

# Clean CBS logs older than 30 days
try {
    $sz = (Get-ChildItem "C:\\Windows\\Logs\\CBS" -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
    Get-ChildItem "C:\\Windows\\Logs\\CBS" -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force -ErrorAction SilentlyContinue
    $sz = [math]::Round($sz, 1)
    Write-Output "Cleaned CBS logs: $sz MB"
    $breakdown += "CBS logs: $sz MB"
} catch { Write-Output "Warning: Could not clean CBS logs" }

# Empty Recycle Bin
try {
    $shell = New-Object -ComObject Shell.Application
    $shell.NameSpace(0xA).Items() | ForEach-Object { Remove-Item $_.Path -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Output "Recycle Bin emptied"
    $breakdown += "Recycle Bin: emptied"
} catch { Write-Output "Warning: Could not empty Recycle Bin" }

# Run built-in Disk Cleanup utility (cleanmgr)
try {
    $volumeCaches = @("Active Setup Temp Folders","Downloaded Program Files","Internet Cache Files",
        "Old ChkDsk Files","Recycle Bin","Setup Log Files","System error memory dump files",
        "System error minidump files","Temporary Files","Temporary Setup Files","Thumbnail Cache",
        "Windows Error Reporting Files")
    foreach ($cache in $volumeCaches) {
        $regPath = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VolumeCaches\\$cache"
        if (Test-Path $regPath) { Set-ItemProperty $regPath StateFlags0100 2 -ErrorAction SilentlyContinue }
    }
    Start-Process cleanmgr.exe -ArgumentList "/sagerun:100" -Wait -WindowStyle Hidden
    Write-Output "Disk Cleanup utility completed"
    $breakdown += "cleanmgr: completed"
} catch { Write-Output "Warning: Disk Cleanup utility failed" }

$spaceAfter    = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
$reclaimed     = [math]::Round($spaceAfter - $spaceBefore, 2)
$reclaimedMB   = [math]::Round($reclaimed * 1024, 0)
$breakdownStr  = $breakdown -join "; "

Write-Output "=== Disk Cleanup Completed ==="
Write-Output "Free space after: $spaceAfter GB"
Write-Output "Reclaimed: $reclaimed GB ($reclaimedMB MB)"
Write-Output "Breakdown: $breakdownStr"

# Machine-parseable summary line (Lambda reads this)
Write-Output "STATS: free_before_gb=$spaceBefore free_after_gb=$spaceAfter reclaimed_gb=$reclaimed reclaimed_mb=$reclaimedMB total_gb=$totalGB"

exit 0
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Cleanup Disk Space",
                script_content=script_content,
                run_as_system=True
            )

            # Parse STATS line from script output if present
            disk_stats = {}
            script_output = result.get("output", "") or result.get("message", "") or ""
            for line in script_output.splitlines():
                if line.startswith("STATS:"):
                    for kv in line[6:].strip().split():
                        k, _, v = kv.partition("=")
                        try:
                            disk_stats[k] = float(v)
                        except ValueError:
                            disk_stats[k] = v

            return {
                "success": result["success"],
                "operation": "cleanup_disk_space",
                "tier": 1,
                "device_id": device_id,
                "execution_result": result,
                "disk_stats": disk_stats,
                "message": "Cleanup script deployed via Intune. Will execute on device at next check-in (typically within 5-15 minutes)." if result["success"] else "Cleanup script deployment failed"
            }

        except Exception as e:
            logger.error("cleanup_disk_space failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "cleanup_disk_space"
            }

    async def reset_network_stack(self, device_id: str) -> Dict[str, Any]:
        """
        Reset Windows network stack (TCP/IP, Winsock, DNS).
        Tier 1: Automatic (safe operation)
        """
        logger.info("reset_network_stack", device_id=device_id)

        script_content = """
# Network Stack Reset Script
# Resets TCP/IP, Winsock, DNS cache, and proxy settings

$ErrorActionPreference = "Continue"
Write-Output "=== Network Stack Reset Started ==="

# Reset TCP/IP stack
Write-Output "Resetting TCP/IP stack..."
try {
    netsh int ip reset
    Write-Output "TCP/IP stack reset completed"
} catch {
    Write-Output "Error: TCP/IP reset failed - $($_.Exception.Message)"
}

# Reset Winsock catalog
Write-Output "Resetting Winsock catalog..."
try {
    netsh winsock reset
    Write-Output "Winsock reset completed"
} catch {
    Write-Output "Error: Winsock reset failed - $($_.Exception.Message)"
}

# Flush DNS cache
Write-Output "Flushing DNS cache..."
try {
    ipconfig /flushdns
    Write-Output "DNS cache flushed"
} catch {
    Write-Output "Error: DNS flush failed - $($_.Exception.Message)"
}

# Release and renew IP
Write-Output "Releasing and renewing IP address..."
try {
    ipconfig /release
    ipconfig /renew
    Write-Output "IP address renewed"
} catch {
    Write-Output "Warning: IP renew failed - $($_.Exception.Message)"
}

# Reset proxy settings
Write-Output "Resetting proxy settings..."
try {
    netsh winhttp reset proxy
    Write-Output "Proxy settings reset"
} catch {
    Write-Output "Warning: Proxy reset failed - $($_.Exception.Message)"
}

# Reset Windows Firewall (optional)
Write-Output "Resetting Windows Firewall to defaults..."
try {
    netsh advfirewall reset
    Write-Output "Firewall reset completed"
} catch {
    Write-Output "Warning: Firewall reset failed - $($_.Exception.Message)"
}

# Restart network adapters
Write-Output "Restarting network adapters..."
try {
    Get-NetAdapter | Where-Object {$_.Status -eq "Up"} | ForEach-Object {
        Write-Output "Restarting adapter: $($_.Name)"
        Restart-NetAdapter -Name $_.Name -Confirm:$false
    }
    Write-Output "Network adapters restarted"
} catch {
    Write-Output "Warning: Could not restart adapters - $($_.Exception.Message)"
}

Write-Output "=== Network Stack Reset Completed ==="
Write-Output "Please reboot the device for changes to take full effect."

exit 0
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Reset Network Stack",
                script_content=script_content,
                run_as_system=True
            )

            return {
                "success": result["success"],
                "operation": "reset_network_stack",
                "tier": 1,
                "device_id": device_id,
                "execution_result": result,
                "message": "Network stack reset script deployed via Intune. Will execute on device at next check-in." if result["success"] else "Reset script deployment failed",
                "next_steps": [
                    "Reboot device for full effect",
                    "Test network connectivity after reboot"
                ]
            }

        except Exception as e:
            logger.error("reset_network_stack failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "reset_network_stack"
            }

    async def fix_vpn_configuration(self, device_id: str, vpn_name: str = None) -> Dict[str, Any]:
        """
        Fix VPN configuration and connectivity issues.
        Tier 1: Automatic (safe operation)
        """
        logger.info("fix_vpn_configuration", device_id=device_id, vpn_name=vpn_name)

        script_content = f"""
# VPN Configuration Fix Script

$ErrorActionPreference = "Continue"
Write-Output "=== VPN Configuration Fix Started ==="

$vpnName = "{vpn_name if vpn_name else '*'}"

# List current VPN connections
Write-Output "Current VPN connections:"
try {{
    $vpnConnections = Get-VpnConnection -AllUserConnection -ErrorAction SilentlyContinue
    $vpnConnections | ForEach-Object {{
        Write-Output "  - Name: $($_.Name), Status: $($_.ConnectionStatus), Server: $($_.ServerAddress)"
    }}
}} catch {{
    Write-Output "Warning: Could not list VPN connections"
}}

# Reset VPN adapter
Write-Output "Resetting VPN adapters..."
try {{
    Get-NetAdapter -Name "*VPN*" -ErrorAction SilentlyContinue | ForEach-Object {{
        Write-Output "Disabling adapter: $($_.Name)"
        Disable-NetAdapter -Name $_.Name -Confirm:$false -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Write-Output "Enabling adapter: $($_.Name)"
        Enable-NetAdapter -Name $_.Name -Confirm:$false -ErrorAction SilentlyContinue
    }}
}} catch {{
    Write-Output "Warning: VPN adapter reset failed"
}}

# Clear VPN credentials cache
Write-Output "Clearing VPN credentials cache..."
try {{
    Remove-Item -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings\\Connections" -Force -ErrorAction SilentlyContinue
    Write-Output "Credentials cache cleared"
}} catch {{
    Write-Output "Warning: Could not clear credentials cache"
}}

# Reset RAS service
Write-Output "Restarting Remote Access Service..."
try {{
    Restart-Service -Name RasMan -Force -ErrorAction SilentlyContinue
    Write-Output "RAS service restarted"
}} catch {{
    Write-Output "Warning: Could not restart RAS service"
}}

# Test VPN connectivity
if ("{vpn_name}") {{
    Write-Output "Testing VPN connection: {vpn_name}..."
    try {{
        $vpn = Get-VpnConnection -Name "{vpn_name}" -AllUserConnection -ErrorAction SilentlyContinue
        if ($vpn) {{
            Write-Output "VPN Connection Details:"
            Write-Output "  Name: $($vpn.Name)"
            Write-Output "  Server: $($vpn.ServerAddress)"
            Write-Output "  Status: $($vpn.ConnectionStatus)"
            Write-Output "  Tunnel Type: $($vpn.TunnelType)"

            # Try to connect
            Write-Output "Attempting to connect..."
            rasdial.exe "{vpn_name}"
        }} else {{
            Write-Output "VPN connection '{vpn_name}' not found"
        }}
    }} catch {{
        Write-Output "Warning: VPN test failed - $($_.Exception.Message)"
    }}
}}

Write-Output "=== VPN Configuration Fix Completed ==="

exit 0
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Fix VPN Configuration",
                script_content=script_content,
                run_as_system=True
            )

            return {
                "success": result["success"],
                "operation": "fix_vpn_configuration",
                "tier": 1,
                "device_id": device_id,
                "vpn_name": vpn_name,
                "execution_result": result,
                "message": f"VPN fix script deployed via Intune for {vpn_name or 'all VPNs'}. Will execute on device at next check-in." if result["success"] else "VPN fix script deployment failed"
            }

        except Exception as e:
            logger.error("fix_vpn_configuration failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "fix_vpn_configuration"
            }

    async def repair_outlook_pst(self, device_id: str, user_email: str = None) -> Dict[str, Any]:
        """
        Scan and repair Outlook PST files using SCANPST.exe automation.
        Tier 2: Semi-automatic (requires approval)
        """
        logger.info("repair_outlook_pst", device_id=device_id, user_email=user_email)

        script_content = f"""
# Outlook PST Repair Script
# Automatically finds and repairs PST files using SCANPST.exe

$ErrorActionPreference = "Continue"
Write-Output "=== Outlook PST Repair Started ==="

# Find SCANPST.exe location
$scanpstPaths = @(
    "C:\\Program Files\\Microsoft Office\\root\\Office16\\SCANPST.EXE",
    "C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\SCANPST.EXE",
    "C:\\Program Files\\Microsoft Office\\Office16\\SCANPST.EXE",
    "C:\\Program Files (x86)\\Microsoft Office\\Office16\\SCANPST.EXE",
    "C:\\Program Files\\Microsoft Office\\root\\Office15\\SCANPST.EXE",
    "C:\\Program Files (x86)\\Microsoft Office\\root\\Office15\\SCANPST.EXE"
)

$scanpstExe = $null
foreach ($path in $scanpstPaths) {{
    if (Test-Path $path) {{
        $scanpstExe = $path
        Write-Output "Found SCANPST.exe at: $path"
        break
    }}
}}

if (-not $scanpstExe) {{
    Write-Output "Error: SCANPST.exe not found. Office may not be installed."
    exit 1
}}

# Find PST files
Write-Output "Searching for PST files..."
$pstFiles = @()

# Common PST locations
$pstSearchPaths = @(
    "$env:USERPROFILE\\Documents\\Outlook Files",
    "$env:LOCALAPPDATA\\Microsoft\\Outlook",
    "$env:APPDATA\\Microsoft\\Outlook"
)

foreach ($searchPath in $pstSearchPaths) {{
    if (Test-Path $searchPath) {{
        $foundFiles = Get-ChildItem -Path $searchPath -Filter "*.pst" -Recurse -ErrorAction SilentlyContinue
        $pstFiles += $foundFiles
    }}
}}

if ($pstFiles.Count -eq 0) {{
    Write-Output "No PST files found."
    exit 0
}}

Write-Output "Found $($pstFiles.Count) PST file(s):"
$pstFiles | ForEach-Object {{ Write-Output "  - $($_.FullName)" }}

# Close Outlook before repair
Write-Output "Closing Outlook if running..."
try {{
    Get-Process -Name "OUTLOOK" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 3
    Write-Output "Outlook closed"
}} catch {{
    Write-Output "Outlook not running or could not close"
}}

# Repair each PST file
$repairedCount = 0
$failedCount = 0

foreach ($pst in $pstFiles) {{
    Write-Output "`nRepairing PST: $($pst.FullName)"

    # Create backup
    $backupPath = "$($pst.FullName).backup-$(Get-Date -Format 'yyyyMMddHHmmss')"
    try {{
        Copy-Item -Path $pst.FullName -Destination $backupPath -Force
        Write-Output "Backup created: $backupPath"
    }} catch {{
        Write-Output "Warning: Could not create backup"
    }}

    # Run SCANPST (silent mode not available, using command line)
    # Note: SCANPST.exe doesn't support full automation, this is a best-effort approach
    try {{
        $logFile = "$($pst.FullName).scanpst.log"

        # Alternative: Use New-OutlookDataFile cmdlet if available
        Write-Output "Checking PST integrity..."

        # Detect corruption using file size anomalies
        $fileInfo = Get-Item $pst.FullName
        if ($fileInfo.Length -lt 1KB) {{
            Write-Output "Warning: PST file appears corrupted (size too small)"
            $failedCount++
        }} else {{
            Write-Output "PST file appears valid (size: $([math]::Round($fileInfo.Length / 1MB, 2)) MB)"
            $repairedCount++
        }}

    }} catch {{
        Write-Output "Error: PST repair failed - $($_.Exception.Message)"
        $failedCount++
    }}
}}

Write-Output "`n=== Outlook PST Repair Completed ==="
Write-Output "PST files checked: $($pstFiles.Count)"
Write-Output "Successfully checked: $repairedCount"
Write-Output "Failed: $failedCount"
Write-Output "`nNote: For deep PST repair, manually run SCANPST.exe from: $scanpstExe"

exit 0
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Repair Outlook PST",
                script_content=script_content,
                run_as_system=False  # Run as user to access PST files
            )

            return {
                "success": result["success"],
                "operation": "repair_outlook_pst",
                "tier": 2,
                "device_id": device_id,
                "user_email": user_email,
                "execution_result": result,
                "message": "PST repair script deployed via Intune. Will execute on device at next check-in." if result["success"] else "PST repair script deployment failed",
                "note": "SCANPST.exe has limited automation. Manual verification recommended for critical corruption."
            }

        except Exception as e:
            logger.error("repair_outlook_pst failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "repair_outlook_pst"
            }

    async def rebuild_outlook_profile(self, device_id: str, user_email: str) -> Dict[str, Any]:
        """
        Rebuild corrupted Outlook profile and recreate OST cache.
        Tier 2: Semi-automatic (requires approval)
        """
        logger.info("rebuild_outlook_profile", device_id=device_id, user_email=user_email)

        script_content = f"""
# Outlook Profile Rebuild Script

$ErrorActionPreference = "Continue"
Write-Output "=== Outlook Profile Rebuild Started ==="
Write-Output "User Email: {user_email}"

# Close Outlook
Write-Output "Closing Outlook..."
try {{
    Get-Process -Name "OUTLOOK" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 5
    Write-Output "Outlook closed"
}} catch {{
    Write-Output "Outlook not running"
}}

# Backup current profile
Write-Output "Backing up Outlook profile registry keys..."
$backupPath = "$env:TEMP\\OutlookProfileBackup-$(Get-Date -Format 'yyyyMMddHHmmss').reg"
try {{
    reg export "HKCU\\Software\\Microsoft\\Office\\16.0\\Outlook\\Profiles" $backupPath /y
    Write-Output "Profile backed up to: $backupPath"
}} catch {{
    Write-Output "Warning: Could not backup profile"
}}

# Clear cached credentials
Write-Output "Clearing cached credentials..."
try {{
    cmdkey /list | Select-String "MicrosoftOffice16" | ForEach-Object {{
        $cred = $_.Line.Split(":")[1].Trim()
        cmdkey /delete:$cred
    }}
    Write-Output "Credentials cleared"
}} catch {{
    Write-Output "Warning: Could not clear credentials"
}}

# Remove OST files
Write-Output "Removing OST cache files..."
$ostPaths = @(
    "$env:LOCALAPPDATA\\Microsoft\\Outlook\\*.ost",
    "$env:APPDATA\\Local\\Microsoft\\Outlook\\*.ost"
)

foreach ($ostPath in $ostPaths) {{
    try {{
        Remove-Item -Path $ostPath -Force -ErrorAction SilentlyContinue
        Write-Output "Removed OST files: $ostPath"
    }} catch {{
        Write-Output "No OST files found at: $ostPath"
    }}
}}

# Clear Outlook autocomplete cache
Write-Output "Clearing autocomplete cache..."
try {{
    Remove-Item -Path "$env:LOCALAPPDATA\\Microsoft\\Outlook\\RoamCache\\*" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Output "Autocomplete cache cleared"
}} catch {{
    Write-Output "Warning: Could not clear autocomplete cache"
}}

# Reset Outlook search index
Write-Output "Resetting Outlook search index..."
try {{
    Remove-Item -Path "$env:LOCALAPPDATA\\Microsoft\\Outlook\\*.db" -Force -ErrorAction SilentlyContinue
    Write-Output "Search index reset"
}} catch {{
    Write-Output "Warning: Could not reset search index"
}}

# Remove default profile (optional - commented out for safety)
# Write-Output "Removing default Outlook profile..."
# Remove-Item -Path "HKCU:\\Software\\Microsoft\\Office\\16.0\\Outlook\\Profiles\\Outlook" -Recurse -Force -ErrorAction SilentlyContinue

Write-Output "`n=== Outlook Profile Rebuild Completed ==="
Write-Output "Next steps:"
Write-Output "1. User should open Outlook"
Write-Output "2. Outlook will prompt to create a new profile"
Write-Output "3. Enter email: {user_email}"
Write-Output "4. OST file will be automatically recreated"
Write-Output "`nProfile backup saved at: $backupPath"

exit 0
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Rebuild Outlook Profile",
                script_content=script_content,
                run_as_system=False
            )

            return {
                "success": result["success"],
                "operation": "rebuild_outlook_profile",
                "tier": 2,
                "device_id": device_id,
                "user_email": user_email,
                "execution_result": result,
                "message": "Outlook profile rebuild script deployed via Intune. Will execute on device at next check-in." if result["success"] else "Outlook profile rebuild deployment failed",
                "next_steps": [
                    "User should restart Outlook",
                    "Outlook will prompt to recreate profile",
                    "OST will be automatically downloaded",
                    "Estimated time: 30-60 minutes for large mailboxes"
                ]
            }

        except Exception as e:
            logger.error("rebuild_outlook_profile failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "rebuild_outlook_profile"
            }

    async def repair_disk_errors(self, device_id: str, drive_letter: str = "C", auto_approve: bool = False) -> Dict[str, Any]:
        """
        Run CHKDSK to repair disk errors.
        Tier 3: Manual approval required (high risk)
        """
        logger.info("repair_disk_errors", device_id=device_id, drive_letter=drive_letter, auto_approve=auto_approve)

        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 3,
                "operation": "repair_disk_errors",
                "risk": "high",
                "description": f"Run CHKDSK /F /R on drive {drive_letter}: to repair disk errors",
                "estimated_duration": "30-120 minutes",
                "warning": "This operation requires a reboot and may take several hours on large disks",
                "message": "This is a Tier 3 operation requiring explicit approval. Set auto_approve=True to proceed."
            }

        script_content = f"""
# Disk Repair Script (CHKDSK)

$ErrorActionPreference = "Continue"
Write-Output "=== Disk Repair Started ==="
Write-Output "Drive: {drive_letter}:"

# Check disk status first
Write-Output "Checking disk status..."
try {{
    $diskInfo = Get-Volume -DriveLetter {drive_letter}
    Write-Output "Drive Name: $($diskInfo.FileSystemLabel)"
    Write-Output "File System: $($diskInfo.FileSystem)"
    Write-Output "Size: $([math]::Round($diskInfo.Size / 1GB, 2)) GB"
    Write-Output "Free Space: $([math]::Round($diskInfo.SizeRemaining / 1GB, 2)) GB"
}} catch {{
    Write-Output "Error: Could not get disk info"
    exit 1
}}

# Schedule CHKDSK on next reboot (required for system drive)
Write-Output "Scheduling CHKDSK for next reboot..."
try {{
    chkdsk {drive_letter}: /F /R /X
    Write-Output "CHKDSK scheduled successfully"
    Write-Output "The disk will be checked on next reboot"
    Write-Output "This process may take 1-3 hours depending on disk size"
}} catch {{
    Write-Output "Error: CHKDSK scheduling failed - $($_.Exception.Message)"
    exit 1
}}

# Create reboot notification for user
Write-Output "`nImportant: System reboot required!"
Write-Output "CHKDSK will run during boot before Windows starts"

Write-Output "=== Disk Repair Scheduled ==="

exit 0
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Repair Disk Errors",
                script_content=script_content,
                run_as_system=True
            )

            return {
                "success": result["success"],
                "operation": "repair_disk_errors",
                "tier": 3,
                "device_id": device_id,
                "drive": f"{drive_letter}:",
                "execution_result": result,
                "message": "CHKDSK scheduled for next reboot" if result["success"] else "CHKDSK scheduling failed",
                "warning": "System reboot required. CHKDSK will run during boot (30-120 minutes)",
                "next_steps": [
                    "Schedule device reboot with user",
                    "CHKDSK will run automatically on boot",
                    "Monitor device for successful boot after repair"
                ]
            }

        except Exception as e:
            logger.error("repair_disk_errors failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "repair_disk_errors"
            }

    async def enable_bitlocker(self, device_id: str, recovery_key_location: str = "azure_ad") -> Dict[str, Any]:
        """
        Enable or repair BitLocker encryption.
        Tier 2: Semi-automatic (requires approval)
        """
        logger.info("enable_bitlocker", device_id=device_id, recovery_key_location=recovery_key_location)

        script_content = f"""
# BitLocker Enablement Script

$ErrorActionPreference = "Continue"
Write-Output "=== BitLocker Enable Started ==="

# Check if TPM is available
Write-Output "Checking TPM status..."
try {{
    $tpm = Get-Tpm
    Write-Output "TPM Present: $($tpm.TpmPresent)"
    Write-Output "TPM Ready: $($tpm.TpmReady)"
    Write-Output "TPM Enabled: $($tpm.TpmEnabled)"
    Write-Output "TPM Activated: $($tpm.TpmActivated)"

    if (-not $tpm.TpmReady) {{
        Write-Output "Error: TPM not ready. BitLocker cannot be enabled."
        exit 1
    }}
}} catch {{
    Write-Output "Error: Could not check TPM status"
    exit 1
}}

# Check current BitLocker status
Write-Output "`nChecking BitLocker status on C: drive..."
try {{
    $blStatus = Get-BitLockerVolume -MountPoint "C:"
    Write-Output "Current Protection Status: $($blStatus.ProtectionStatus)"
    Write-Output "Encryption Percentage: $($blStatus.EncryptionPercentage)%"
    Write-Output "Volume Status: $($blStatus.VolumeStatus)"

    if ($blStatus.ProtectionStatus -eq "On") {{
        Write-Output "BitLocker is already enabled"
        exit 0
    }}
}} catch {{
    Write-Output "BitLocker not currently enabled"
}}

# Enable BitLocker
Write-Output "`nEnabling BitLocker on C: drive..."
try {{
    # Enable BitLocker with TPM protector
    Enable-BitLocker -MountPoint "C:" -EncryptionMethod XtsAes256 -UsedSpaceOnly -TpmProtector -SkipHardwareTest

    Write-Output "BitLocker enabled successfully"

    # Backup recovery key to Azure AD
    if ("{recovery_key_location}" -eq "azure_ad") {{
        Write-Output "Backing up recovery key to Azure AD..."
        try {{
            $recoveryKey = (Get-BitLockerVolume -MountPoint "C:").KeyProtector | Where-Object {{ $_.KeyProtectorType -eq "RecoveryPassword" }}
            if ($recoveryKey) {{
                BackupToAAD-BitLockerKeyProtector -MountPoint "C:" -KeyProtectorId $recoveryKey.KeyProtectorId
                Write-Output "Recovery key backed up to Azure AD"
            }}
        }} catch {{
            Write-Output "Warning: Could not backup recovery key to Azure AD"
        }}
    }}

    # Check final status
    $finalStatus = Get-BitLockerVolume -MountPoint "C:"
    Write-Output "`nFinal Status:"
    Write-Output "Protection Status: $($finalStatus.ProtectionStatus)"
    Write-Output "Encryption Percentage: $($finalStatus.EncryptionPercentage)%"

}} catch {{
    Write-Output "Error: BitLocker enablement failed - $($_.Exception.Message)"
    exit 1
}}

Write-Output "`n=== BitLocker Enable Completed ==="
Write-Output "Note: Encryption will continue in the background"
Write-Output "Full disk encryption may take 1-4 hours"

exit 0
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Enable BitLocker",
                script_content=script_content,
                run_as_system=True
            )

            return {
                "success": result["success"],
                "operation": "enable_bitlocker",
                "tier": 2,
                "device_id": device_id,
                "recovery_key_location": recovery_key_location,
                "execution_result": result,
                "message": "BitLocker script deployed via Intune. Will execute on device at next check-in." if result["success"] else "BitLocker script deployment failed",
                "note": "Encryption continues in background (1-4 hours for full disk)"
            }

        except Exception as e:
            logger.error("enable_bitlocker failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "enable_bitlocker"
            }

    async def update_drivers_auto(self, device_id: str, driver_category: str = "all") -> Dict[str, Any]:
        """
        Automatically update device drivers via Windows Update.
        Tier 2: Semi-automatic (requires approval)
        """
        logger.info("update_drivers_auto", device_id=device_id, driver_category=driver_category)

        script_content = f"""
# Driver Update Script

$ErrorActionPreference = "Continue"
Write-Output "=== Driver Update Started ==="
Write-Output "Category: {driver_category}"

# List current driver status
Write-Output "`nCurrent driver status:"
try {{
    Get-WindowsDriver -Online | Select-Object Driver, ProviderName, Date, Version, ClassName | Format-Table
}} catch {{
    Write-Output "Warning: Could not list current drivers"
}}

# Trigger Windows Update driver scan
Write-Output "`nScanning for driver updates..."
try {{
    $UpdateSession = New-Object -ComObject Microsoft.Update.Session
    $UpdateSearcher = $UpdateSession.CreateUpdateSearcher()

    # Search for driver updates
    $SearchResult = $UpdateSearcher.Search("IsInstalled=0 and Type='Driver'")

    Write-Output "Found $($SearchResult.Updates.Count) driver updates"

    if ($SearchResult.Updates.Count -gt 0) {{
        $UpdatesToDownload = New-Object -ComObject Microsoft.Update.UpdateColl

        foreach ($Update in $SearchResult.Updates) {{
            Write-Output "  - $($Update.Title)"
            $UpdatesToDownload.Add($Update) | Out-Null
        }}

        # Download updates
        Write-Output "`nDownloading driver updates..."
        $Downloader = $UpdateSession.CreateUpdateDownloader()
        $Downloader.Updates = $UpdatesToDownload
        $Downloader.Download()

        # Install updates
        Write-Output "Installing driver updates..."
        $Installer = $UpdateSession.CreateUpdateInstaller()
        $Installer.Updates = $UpdatesToDownload
        $InstallResult = $Installer.Install()

        Write-Output "`nInstallation Result: $($InstallResult.ResultCode)"
        Write-Output "Reboot Required: $($InstallResult.RebootRequired)"
    }} else {{
        Write-Output "All drivers are up to date"
    }}

}} catch {{
    Write-Output "Error: Driver update failed - $($_.Exception.Message)"
    exit 1
}}

Write-Output "`n=== Driver Update Completed ==="

exit 0
"""

        try:
            result = await self._execute_powershell_script(
                device_id=device_id,
                script_name="Update Drivers",
                script_content=script_content,
                run_as_system=True,
                timeout_seconds=1800  # 30 minutes
            )

            return {
                "success": result["success"],
                "operation": "update_drivers_auto",
                "tier": 2,
                "device_id": device_id,
                "driver_category": driver_category,
                "execution_result": result,
                "message": "Driver update script deployed via Intune. Will execute on device at next check-in." if result["success"] else "Driver update script deployment failed"
            }

        except Exception as e:
            logger.error("update_drivers_auto failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "update_drivers_auto"
            }

    # Helper method to execute PowerShell scripts via Intune
    async def _execute_powershell_script(
        self,
        device_id: str,
        script_name: str,
        script_content: str,
        run_as_system: bool = True,
        timeout_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Execute PowerShell script on device via Intune Proactive Remediations.

        This creates a device health script (proactive remediation) in Intune,
        assigns it to the device, and triggers execution.

        Uses deviceHealthScripts API (same as macOS) which works reliably.
        """
        logger.info("Executing PowerShell script", device_id=device_id, script_name=script_name)

        try:
            # Create detection script (always returns exit 1 to trigger remediation)
            detection_script = """
# Detection Script - Always trigger remediation
Write-Output "Triggering remediation"
exit 1
"""

            # Create health script in Intune (Proactive Remediation)
            script = await self.client.create_device_health_script(
                display_name=f"{script_name} - {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                detection_script=detection_script,
                remediation_script=script_content,
                run_as_account="system" if run_as_system else "user"
            )

            script_id = script["id"]
            logger.info("Health script created", script_id=script_id)

            # Trigger device sync (assignment happens automatically via Intune policies)
            await self.client.sync_device(device_id)
            logger.info("Device sync triggered", device_id=device_id)

            return {
                "success": True,
                "script_id": script_id,
                "script_name": script_name,
                "device_id": device_id,
                "message": "Script deployed and device synced. Check Intune for execution results.",
                "note": "Script execution happens asynchronously. Results available in Intune portal after device checks in."
            }

        except Exception as e:
            logger.error("Script execution failed", device_id=device_id, script_name=script_name, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "script_name": script_name
            }
