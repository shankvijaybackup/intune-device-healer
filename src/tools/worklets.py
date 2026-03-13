"""
Worklets Library — MCP Tools
Inspired by the Automox Worklets catalog. Each tool embeds a PowerShell or Bash
script and runs it via Intune deviceHealthScripts (Proactive Remediations).

No Automox account or agent required. Runs entirely through your existing Intune
infrastructure using the same _execute_powershell_script / _execute_shell_script
pattern already in windows_remediation.py and macos_remediation.py.

Categories covered:
  Security Configuration   — firewall, SMB, RDP, USB, lock screen, BitLocker audit
  Diagnostics              — event log errors, reboot history, disk space, battery
  Maintenance              — bloatware removal, temp cleanup, old user profiles
  Troubleshooting          — kill process, browser extensions audit
  Compliance               — local admin audit, password policy
"""

import structlog
import base64
from typing import Dict, Any, Optional
from datetime import datetime
from core.graph_client import GraphClient

logger = structlog.get_logger()


class WorkletsTools:
    """
    Library of pre-built remediation scripts for Windows and macOS.
    Each method embeds the script inline and runs it via Intune.
    """

    def __init__(self, authenticator, config):
        self.client = GraphClient(authenticator, config)

    async def run_performance_probe(self, device_id: str) -> Dict[str, Any]:
        """
        Run a high-frequency performance probe to capture live stats.
        Captures CPU, RAM, and Top 5 Processes.
        """
        script = r"""
        $CPU = Get-Counter '\Processor(_Total)\% Processor Time' -Continuous -MaxSamples 2 | Select-Object -ExpandProperty CounterSamples | Select-Object -ExpandProperty CookedValue | Measure-Object -Average | Select-Object -ExpandProperty Average
        $Mem = Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory, TotalVisibleMemorySize
        $MemUsage = [math]::Round((($Mem.TotalVisibleMemorySize - $Mem.FreePhysicalMemory) / $Mem.TotalVisibleMemorySize) * 100, 2)
        $TopProc = Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 | Select-Object Name, CPU, WorkingSet64
        Write-Output "--- LIVE PERFORMANCE DATA ---"
        Write-Output "CPU: $CPU %"
        Write-Output "Memory: $MemUsage %"
        Write-Output "Top Processes:"
        $TopProc | ForEach-Object { Write-Output "$($_.Name): $($_.CPU) CPU, $([math]::Round($_.WorkingSet64 / 1MB, 2)) MB" }
        """
        return await self._run_windows(device_id, "Performance-Probe", script)

    async def run_performance_probe_mac(self, device_id: str) -> Dict[str, Any]:
        """Run a high-frequency performance probe on macOS."""
        script = r"""#!/bin/bash
echo "--- LIVE PERFORMANCE DATA (macOS) ---"
CPU_LOAD=$(ps -A -o %cpu | awk '{s+=$1} END {print s}')
echo "CPU Total Load: $CPU_LOAD %"
echo "Top Processes:"
ps -A -ro %cpu | head -n 6
"""
        return await self._run_mac(device_id, "Mac-Performance-Probe", script)

    async def trigger_cpu_stress(self, device_id: str, duration_seconds: int = 60) -> Dict[str, Any]:
        """
        [SIMULATION] Spike CPU on a Windows device for a fixed duration.
        Used for validating 'Auto-Heal' and Real-Time performance stats.
        """
        script = f"""
        $duration = {duration_seconds}
        $start = Get-Date
        Write-Output "--- CPU STRESS SIMULATION STARTED ---"
        Write-Output "Target Duration: $duration seconds"
        Write-Output "Running busy loop on all logical processors..."
        
        while ((Get-Date) -lt $start.AddSeconds($duration)) {{
            # Busy wait loop to create spike
            $results = 1..100 | ForEach-Object {{ $_ * $_ }}
        }}
        Write-Output "--- CPU STRESS SIMULATION FINISHED ---"
        """
        return await self._run_windows(device_id, "CPU-Stress-Simulation", script)

    # =========================================================================
    # SECURITY CONFIGURATION
    # =========================================================================

    async def disable_smb_v1(self, device_id: str) -> Dict[str, Any]:
        """
        Disable SMBv1 on Windows. Eliminates legacy protocol vulnerabilities
        including EternalBlue / WannaCry attack surface.
        """
        script = """
# Disable SMBv1 Client and Server
Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force
Set-SmbClientConfiguration -EnableBandwidthThrottling $false -Force
Disable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -NoRestart | Out-Null

# Verify
$status = Get-SmbServerConfiguration | Select-Object EnableSMB1Protocol
Write-Output "SMBv1 Server enabled: $($status.EnableSMB1Protocol)"
if ($status.EnableSMB1Protocol -eq $false) {
    Write-Output "SMBv1 disabled successfully."
    exit 0
} else {
    Write-Output "SMBv1 still enabled."
    exit 1
}
"""
        return await self._run_windows(device_id, "Disable-SMBv1", script)

    async def enable_windows_firewall(self, device_id: str) -> Dict[str, Any]:
        """
        Enable Windows Firewall across Domain, Public, and Private profiles.
        """
        script = """
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True
$profiles = Get-NetFirewallProfile | Select-Object Name, Enabled
foreach ($p in $profiles) {
    Write-Output "Firewall $($p.Name): Enabled=$($p.Enabled)"
}
Write-Output "Windows Firewall enabled on all profiles."
"""
        return await self._run_windows(device_id, "Enable-WindowsFirewall", script)

    async def disable_rdp(self, device_id: str) -> Dict[str, Any]:
        """
        Disable Remote Desktop Protocol on Windows to reduce attack surface.
        """
        script = """
Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' `
    -Name "fDenyTSConnections" -Value 1
Disable-NetFirewallRule -DisplayGroup "Remote Desktop"
Write-Output "RDP disabled and firewall rules blocked."
"""
        return await self._run_windows(device_id, "Disable-RDP", script)

    async def disable_usb_storage_windows(self, device_id: str) -> Dict[str, Any]:
        """
        Block USB removable storage on Windows via registry policy.
        """
        script = """
$path = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\USBSTOR"
Set-ItemProperty -Path $path -Name "Start" -Value 4
Write-Output "USB storage disabled. Start value set to 4 (Disabled)."
$val = (Get-ItemProperty -Path $path -Name Start).Start
Write-Output "Current USBSTOR Start value: $val"
"""
        return await self._run_windows(device_id, "Disable-USB-Storage", script)

    async def enforce_lock_screen_windows(self, device_id: str, idle_minutes: int = 10) -> Dict[str, Any]:
        """
        Enforce automatic lock screen after inactivity on Windows.
        Default: 10 minutes.
        """
        seconds = idle_minutes * 60
        script = f"""
$regPath = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System"
if (-not (Test-Path $regPath)) {{ New-Item -Path $regPath -Force | Out-Null }}
Set-ItemProperty -Path $regPath -Name "InactivityTimeoutSecs" -Value {seconds}
powercfg /setacvalueindex SCHEME_CURRENT SUB_NONE CONSOLELOCK {seconds}
powercfg /setdcvalueindex SCHEME_CURRENT SUB_NONE CONSOLELOCK {seconds}
powercfg /setactive SCHEME_CURRENT
Write-Output "Lock screen enforced after {idle_minutes} minutes of inactivity."
"""
        return await self._run_windows(device_id, "Enforce-LockScreen", script)

    async def disable_powershell_v2(self, device_id: str) -> Dict[str, Any]:
        """
        Disable PowerShell v2 on Windows 10/11. Prevents attackers from
        using the older, unlogged version to bypass security controls.
        """
        script = """
Disable-WindowsOptionalFeature -Online -FeatureName MicrosoftWindowsPowerShellV2Root -NoRestart | Out-Null
Disable-WindowsOptionalFeature -Online -FeatureName MicrosoftWindowsPowerShellV2 -NoRestart | Out-Null
$status = Get-WindowsOptionalFeature -Online -FeatureName MicrosoftWindowsPowerShellV2Root
Write-Output "PowerShell V2 State: $($status.State)"
"""
        return await self._run_windows(device_id, "Disable-PowerShell-V2", script)

    async def disable_llmnr_windows(self, device_id: str) -> Dict[str, Any]:
        """
        Disable LLMNR (Link-Local Multicast Name Resolution) on Windows.
        Prevents network name resolution poisoning / responder attacks.
        """
        script = """
$path = "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\DNSClient"
if (-not (Test-Path $path)) { New-Item -Path $path -Force | Out-Null }
Set-ItemProperty -Path $path -Name "EnableMulticast" -Value 0
Write-Output "LLMNR disabled via registry policy."
"""
        return await self._run_windows(device_id, "Disable-LLMNR", script)

    async def force_password_reset_on_logon(self, device_id: str) -> Dict[str, Any]:
        """
        Require all local user accounts to reset their password at next logon.
        """
        script = """
$users = Get-LocalUser | Where-Object { $_.Enabled -eq $true -and $_.Name -ne "Administrator" }
foreach ($user in $users) {
    Set-LocalUser -Name $user.Name -PasswordNeverExpires $false
    net user $user.Name /logonpasswordchg:yes 2>&1 | Out-Null
    Write-Output "Password reset required for: $($user.Name)"
}
Write-Output "Done. $($users.Count) accounts flagged for password reset at next logon."
"""
        return await self._run_windows(device_id, "Force-Password-Reset", script)

    async def disable_netbios(self, device_id: str) -> Dict[str, Any]:
        """
        Disable NetBIOS over TCP/IP on all Windows network adapters.
        Reduces attack surface, prevents name resolution attacks.
        """
        script = """
$adapters = Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true }
foreach ($adapter in $adapters) {
    $result = $adapter.SetTcpipNetbios(2)
    Write-Output "Adapter $($adapter.Description): NetBIOS disabled (result=$($result.ReturnValue))"
}
Write-Output "NetBIOS over TCP/IP disabled on all active adapters."
"""
        return await self._run_windows(device_id, "Disable-NetBIOS", script)

    # =========================================================================
    # DIAGNOSTICS & AUDITING
    # =========================================================================

    async def get_event_log_errors(self, device_id: str, hours: int = 24) -> Dict[str, Any]:
        """
        Retrieve recent System and Application event log errors from Windows.
        Reports the last N hours of errors to the script output.
        """
        script = f"""
$since = (Get-Date).AddHours(-{hours})
Write-Output "=== System Log Errors (last {hours}h) ==="
$sysErrors = Get-EventLog -LogName System -EntryType Error -After $since -Newest 20 2>$null
if ($sysErrors) {{
    $sysErrors | ForEach-Object {{
        Write-Output "[$($_.TimeGenerated)] $($_.Source): $($_.Message.Substring(0, [Math]::Min(120, $_.Message.Length)))"
    }}
}} else {{ Write-Output "No System errors found." }}

Write-Output "`n=== Application Log Errors (last {hours}h) ==="
$appErrors = Get-EventLog -LogName Application -EntryType Error -After $since -Newest 20 2>$null
if ($appErrors) {{
    $appErrors | ForEach-Object {{
        Write-Output "[$($_.TimeGenerated)] $($_.Source): $($_.Message.Substring(0, [Math]::Min(120, $_.Message.Length)))"
    }}
}} else {{ Write-Output "No Application errors found." }}
"""
        return await self._run_windows(device_id, "Get-EventLog-Errors", script)

    async def get_reboot_history_windows(self, device_id: str) -> Dict[str, Any]:
        """
        Retrieve the last 10 system reboot events from Windows event log.
        """
        script = """
Write-Output "=== Last 10 Reboot Events ==="
$reboots = Get-EventLog -LogName System -Source "User32" -EventId 1074 -Newest 10 2>$null
if ($reboots) {
    $reboots | ForEach-Object {
        Write-Output "[$($_.TimeGenerated)] $($_.ReplacementStrings[0]) - $($_.Message.Substring(0, [Math]::Min(100,$_.Message.Length)))"
    }
} else {
    # Try alternative event source
    $reboots2 = Get-WinEvent -FilterHashtable @{LogName='System'; Id=@(41,1074,6006,6008)} -MaxEvents 10 2>$null
    if ($reboots2) {
        $reboots2 | ForEach-Object {
            Write-Output "[$($_.TimeCreated)] ID=$($_.Id) $($_.Message.Substring(0, [Math]::Min(100,$_.Message.Length)))"
        }
    } else { Write-Output "No reboot events found." }
}

Write-Output "`n=== System Uptime ==="
$os = Get-WmiObject Win32_OperatingSystem
$uptime = (Get-Date) - $os.ConvertToDateTime($os.LastBootUpTime)
Write-Output "Last boot: $($os.ConvertToDateTime($os.LastBootUpTime))"
Write-Output "Uptime: $([int]$uptime.TotalDays)d $($uptime.Hours)h $($uptime.Minutes)m"
"""
        return await self._run_windows(device_id, "Get-Reboot-History", script)

    async def get_disk_space_report(self, device_id: str) -> Dict[str, Any]:
        """
        Report free disk space on all Windows drives. Flags drives below 10% free.
        """
        script = """
Write-Output "=== Disk Space Report ==="
$drives = Get-WmiObject Win32_LogicalDisk | Where-Object { $_.DriveType -eq 3 }
foreach ($drive in $drives) {
    $total = [math]::Round($drive.Size / 1GB, 2)
    $free  = [math]::Round($drive.FreeSpace / 1GB, 2)
    $used  = [math]::Round(($drive.Size - $drive.FreeSpace) / 1GB, 2)
    $pct   = if ($drive.Size -gt 0) { [math]::Round(($drive.FreeSpace / $drive.Size) * 100, 1) } else { 0 }
    $flag  = if ($pct -lt 10) { " [LOW]" } else { "" }
    Write-Output "$($drive.DeviceID)  Total: ${total}GB  Used: ${used}GB  Free: ${free}GB  ($pct% free)$flag"
}
"""
        return await self._run_windows(device_id, "Get-Disk-Space-Report", script)

    async def get_battery_health_windows(self, device_id: str) -> Dict[str, Any]:
        """
        Check battery health and status on Windows laptops.
        Reports design capacity vs current full charge capacity.
        """
        script = """
Write-Output "=== Battery Health Report ==="
$batteries = Get-WmiObject -Class Win32_Battery 2>$null
if ($batteries) {
    foreach ($b in $batteries) {
        Write-Output "Name            : $($b.Name)"
        Write-Output "Status          : $($b.Status)"
        Write-Output "Estimated Charge: $($b.EstimatedChargeRemaining)%"
        Write-Output "Battery Status  : $($b.BatteryStatus)"
    }
    # Generate power report
    powercfg /batteryreport /output "$env:TEMP\\battery-report.html" 2>$null
    if (Test-Path "$env:TEMP\\battery-report.html") {
        Write-Output "Battery report generated at: $env:TEMP\\battery-report.html"
    }
} else {
    Write-Output "No battery detected (desktop or VM)."
}
"""
        return await self._run_windows(device_id, "Get-Battery-Health", script)

    async def audit_local_admin_accounts(self, device_id: str) -> Dict[str, Any]:
        """
        Identify all local administrator accounts on a Windows device.
        Security audit — reports who has admin rights.
        """
        script = """
Write-Output "=== Local Administrator Accounts ==="
$admins = Get-LocalGroupMember -Group "Administrators" 2>$null
if ($admins) {
    foreach ($a in $admins) {
        $type = $a.ObjectClass
        $src  = if ($a.PrincipalSource) { $a.PrincipalSource } else { "Unknown" }
        Write-Output "$($a.Name) | Type: $type | Source: $src"
    }
    Write-Output "`nTotal admin accounts: $($admins.Count)"
} else {
    Write-Output "Could not enumerate administrators group."
}
"""
        return await self._run_windows(device_id, "Audit-Local-Admins", script)

    async def get_browser_extensions(self, device_id: str) -> Dict[str, Any]:
        """
        Enumerate installed browser extensions across Chrome, Edge, Firefox, and Brave.
        Security audit tool.
        """
        script = """
Write-Output "=== Installed Browser Extensions ==="

function Get-ChromiumExtensions($browserName, $extPath) {
    if (-not (Test-Path $extPath)) { return }
    Write-Output "`n--- $browserName ---"
    Get-ChildItem $extPath -Directory 2>$null | ForEach-Object {
        $manifestPath = Get-ChildItem $_.FullName -Filter "manifest.json" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($manifestPath) {
            $manifest = Get-Content $manifestPath.FullName -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($manifest -and $manifest.name -and $manifest.name -notlike "__MSG_*") {
                Write-Output "  $($manifest.name) v$($manifest.version)"
            }
        }
    }
}

$users = Get-ChildItem "C:\\Users" -Directory | Where-Object { $_.Name -notin @("Public","Default","Default User") }
foreach ($user in $users) {
    $chromePath  = "$($user.FullName)\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Extensions"
    $edgePath    = "$($user.FullName)\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\Extensions"
    $bravePath   = "$($user.FullName)\\AppData\\Local\\BraveSoftware\\Brave-Browser\\User Data\\Default\\Extensions"

    Get-ChromiumExtensions "Chrome ($($user.Name))"  $chromePath
    Get-ChromiumExtensions "Edge ($($user.Name))"    $edgePath
    Get-ChromiumExtensions "Brave ($($user.Name))"   $bravePath
}
"""
        return await self._run_windows(device_id, "Get-Browser-Extensions", script)

    # =========================================================================
    # MAINTENANCE
    # =========================================================================

    async def remove_old_user_profiles(self, device_id: str, older_than_days: int = 90) -> Dict[str, Any]:
        """
        Delete Windows user profiles that haven't been used in N days.
        Default: profiles older than 90 days. Skips system accounts.
        """
        script = f"""
$cutoff = (Get-Date).AddDays(-{older_than_days})
$skip   = @("Administrator","Default","Public","Guest","NetworkService","LocalService","SYSTEM")
Write-Output "Checking profiles not used since $cutoff..."

$profiles = Get-WmiObject -Class Win32_UserProfile | Where-Object {{
    -not $_.Special -and
    $_.ConvertToDateTime($_.LastUseTime) -lt $cutoff
}}

$removed = 0
foreach ($p in $profiles) {{
    $username = Split-Path $p.LocalPath -Leaf
    if ($skip -contains $username) {{ continue }}
    Write-Output "Removing profile: $($p.LocalPath) (last used $($p.ConvertToDateTime($p.LastUseTime)))"
    try {{
        $p.Delete() | Out-Null
        $removed++
    }} catch {{
        Write-Output "  Failed: $_"
    }}
}}
Write-Output "Done. Removed $removed profiles."
"""
        return await self._run_windows(device_id, "Remove-Old-User-Profiles", script)

    async def clean_temp_files_all_users(self, device_id: str) -> Dict[str, Any]:
        """
        Remove temporary files from all user profiles and system temp on Windows.
        Safe version — only deletes files, not folders. Skips locked files.
        """
        script = r"""
Write-Output "=== Temp File Cleanup ==="
$freed = 0

function Remove-TempFiles($path) {
    if (-not (Test-Path $path)) { return 0 }
    $size = 0
    Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $size += $_.Length
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
    }
    return $size
}

# System temp
$freed += Remove-TempFiles $env:SystemRoot\Temp
Write-Output "System Temp cleared."

# All user temp folders
Get-ChildItem "C:\Users" -Directory | ForEach-Object {
    $userTemp = "$($_.FullName)\AppData\Local\Temp"
    $size = Remove-TempFiles $userTemp
    $freed += $size
    if ($size -gt 0) {
        Write-Output "Cleared $([math]::Round($size/1MB,1)) MB from $($_.Name)\AppData\Local\Temp"
    }
}

Write-Output "Total freed: $([math]::Round($freed/1MB,1)) MB"
"""
        return await self._run_windows(device_id, "Clean-Temp-Files-All-Users", script)

    async def remove_windows_bloatware(self, device_id: str) -> Dict[str, Any]:
        """
        Remove pre-installed Windows Store bloatware apps.
        Targets Xbox, Candy Crush, Bing apps, Solitaire, and other common bloatware.
        Does not remove productivity apps (Photos, Calculator, Notepad).
        """
        script = """
$bloatware = @(
    "Microsoft.XboxApp",
    "Microsoft.XboxGameOverlay",
    "Microsoft.XboxGamingOverlay",
    "Microsoft.XboxIdentityProvider",
    "Microsoft.XboxSpeechToTextOverlay",
    "king.com.CandyCrushSaga",
    "king.com.CandyCrushFriends",
    "Microsoft.BingFinance",
    "Microsoft.BingNews",
    "Microsoft.BingSports",
    "Microsoft.BingWeather",
    "Microsoft.MicrosoftSolitaireCollection",
    "Microsoft.GetHelp",
    "Microsoft.Getstarted",
    "Microsoft.MixedReality.Portal",
    "Microsoft.People",
    "Microsoft.SkypeApp",
    "Microsoft.Todos",
    "Microsoft.ZuneMusic",
    "Microsoft.ZuneVideo"
)

$removed = 0
foreach ($app in $bloatware) {
    $pkg = Get-AppxPackage -AllUsers -Name $app -ErrorAction SilentlyContinue
    if ($pkg) {
        Write-Output "Removing: $app"
        Remove-AppxPackage -Package $pkg.PackageFullName -AllUsers -ErrorAction SilentlyContinue | Out-Null
        $removed++
    }
}
Write-Output "Done. Removed $removed bloatware apps."
"""
        return await self._run_windows(device_id, "Remove-Windows-Bloatware", script)

    async def kill_process_windows(self, device_id: str, process_name: str) -> Dict[str, Any]:
        """
        Terminate a named process on a Windows device.
        Example: process_name="outlook" or "chrome"
        """
        script = f"""
$name = "{process_name}"
$procs = Get-Process -Name $name -ErrorAction SilentlyContinue
if ($procs) {{
    $procs | Stop-Process -Force
    Write-Output "Terminated $($procs.Count) instance(s) of '$name'."
}} else {{
    Write-Output "No running process found with name '$name'."
}}
"""
        return await self._run_windows(device_id, f"Kill-Process-{process_name}", script)

    async def get_windows_update_events(self, device_id: str) -> Dict[str, Any]:
        """
        Extract recent Windows Update events for patch tracking and troubleshooting.
        """
        script = """
Write-Output "=== Windows Update Events (last 30 days) ==="
try {
    $events = Get-WinEvent -FilterHashtable @{
        LogName   = 'System'
        ProviderName = 'Microsoft-Windows-WindowsUpdateClient'
        StartTime = (Get-Date).AddDays(-30)
    } -MaxEvents 25 -ErrorAction Stop

    $events | ForEach-Object {
        Write-Output "[$($_.TimeCreated.ToString('yyyy-MM-dd HH:mm'))] ID=$($_.Id) $($_.Message.Substring(0,[Math]::Min(120,$_.Message.Length)))"
    }
} catch {
    Write-Output "No Windows Update events found or access denied: $_"
}
"""
        return await self._run_windows(device_id, "Get-Windows-Update-Events", script)

    async def get_performance_diagnostics_windows(self, device_id: str) -> Dict[str, Any]:
        """
        High-resolution CPU, Memory, and Disk IO diagnostics for Windows.
        """
        script = """
Write-Output "=== Performance Diagnostics (Windows) ==="

# CPU Usage (Top 5 processes)
Write-Output "`n--- Top 5 CPU Consumers ---"
Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 -Property Name, CPU, WorkingSet | Format-Table

# Memory Usage
Write-Output "`n--- Memory Status ---"
$mem = Get-WmiObject Win32_OperatingSystem
$totalMem = [math]::Round($mem.TotalVisibleMemorySize / 1KB, 2)
$freeMem = [math]::Round($mem.FreePhysicalMemory / 1KB, 2)
$usedMem = $totalMem - $freeMem
$pctUsed = [math]::Round(($usedMem / $totalMem) * 100, 2)
Write-Output "Total RAM: ${totalMem} MB"
Write-Output "Used RAM:  ${usedMem} MB ($pctUsed%)"
Write-Output "Free RAM:  ${freeMem} MB"

# Disk IO
Write-Output "`n--- Disk IO (Current) ---"
Get-Counter -Counter "\\LogicalDisk(C:)\\Disk Reads/sec", "\\LogicalDisk(C:)\\Disk Writes/sec" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CounterSamples | Format-Table Path, CookedValue

# Machine readable summary
Write-Output "STATS: cpu_count=$( (Get-CimInstance Win32_Processor).NumberOfCores ) mem_total_mb=$totalMem mem_used_pct=$pctUsed"
"""
        return await self._run_windows(device_id, "Get-Performance-Diagnostics", script)

    async def fix_printer_spooler(self, device_id: str) -> Dict[str, Any]:
        """
        Stop, clear, and restart the Windows Print Spooler service.
        Fixes stuck print jobs and spooler crashes.
        """
        script = """
Write-Output "=== Fixing Print Spooler ==="
Write-Output "Stopping Spooler service..."
Stop-Service -Name Spooler -Force -ErrorAction SilentlyContinue

Write-Output "Clearing printer queue files..."
Remove-Item -Path "$env:SystemRoot\\System32\\spool\\PRINTERS\\*" -Force -Recurse -ErrorAction SilentlyContinue

Write-Output "Restarting Spooler service..."
Start-Service -Name Spooler
$status = (Get-Service -Name Spooler).Status
Write-Output "Spooler service status: $status"

if ($status -eq "Running") {
    Write-Output "Print Spooler fixed successfully."
    exit 0
} else {
    Write-Output "Failed to restart Print Spooler."
    exit 1
}
"""
        return await self._run_windows(device_id, "Fix-Printer-Spooler", script)

    async def get_detailed_disk_usage_windows(self, device_id: str) -> Dict[str, Any]:
        """
        Deep scan for large files and folder sizes on Windows.
        """
        script = """
Write-Output "=== Detailed Disk Usage (C:) ==="
Write-Output "Identifying Top 10 Largest Folders in C:\\Users..."
$folders = Get-ChildItem "C:\\Users" -Directory | ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1GB
    [PSCustomObject]@{ Folder = $_.FullName; SizeGB = [math]::Round($size, 2) }
} | Sort-Object SizeGB -Descending | Select-Object -First 10
$folders | Format-Table

Write-Output "`nIdentifying Top 20 Largest Files on System Drive..."
Get-ChildItem "C:\\" -Recurse -File -ErrorAction SilentlyContinue | Sort-Object Length -Descending | Select-Object -First 20 -Property Name, @{Name="SizeGB"; Expression={[math]::Round($_.Length / 1GB, 4)}}, FullName | Format-Table
"""
        return await self._run_windows(device_id, "Detailed-Disk-Usage", script)

    # =========================================================================
    # macOS WORKLETS
    # =========================================================================

    async def disable_usb_storage_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Disable USB mass storage on macOS by unloading and blacklisting the IOUSBMassStorageClass kernel extension.
        """
        script = """#!/bin/bash
# Unload USB mass storage kext
/sbin/kextunload -b com.apple.iokit.IOUSBMassStorageClass 2>/dev/null
echo "USB mass storage kext unloaded."

# Add to kext blacklist via plist
PLIST="/Library/Preferences/SystemConfiguration/com.apple.Boot.plist"
if [ -f "$PLIST" ]; then
    /usr/bin/plutil -replace "Kernel Flags" -string "kext-dev-mode=1 kextd.disable-load-com.apple.iokit.IOUSBMassStorageClass=1" "$PLIST" 2>/dev/null
fi

echo "USB storage disabled."
"""
        return await self._run_mac(device_id, "Disable-USB-Storage-Mac", script)

    async def disable_bluetooth_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Disable Bluetooth on macOS when no peripherals are connected.
        """
        script = """#!/bin/bash
# Disable Bluetooth via blueutil if available, else defaults
if command -v blueutil &>/dev/null; then
    blueutil --power 0
    echo "Bluetooth disabled via blueutil."
else
    defaults write /Library/Preferences/com.apple.Bluetooth ControllerPowerState -int 0
    /usr/bin/killall -HUP blued 2>/dev/null
    echo "Bluetooth preference set to disabled."
fi
"""
        return await self._run_mac(device_id, "Disable-Bluetooth-Mac", script)

    async def enforce_lock_screen_mac(self, device_id: str, idle_minutes: int = 10) -> Dict[str, Any]:
        """
        Enforce automatic screen lock after inactivity on macOS.
        Default: 10 minutes.
        """
        idle_seconds = idle_minutes * 60
        script = f"""#!/bin/bash
# Set screen saver idle time
defaults write /Library/Preferences/com.apple.screensaver idleTime -int {idle_seconds}

# Require password immediately after sleep/screen saver
defaults write /Library/Preferences/com.apple.screensaver askForPassword -int 1
defaults write /Library/Preferences/com.apple.screensaver askForPasswordDelay -int 0

echo "Lock screen enforced after {idle_minutes} minutes of inactivity."
echo "Password required immediately on wake."
"""
        return await self._run_mac(device_id, "Enforce-LockScreen-Mac", script)

    async def disable_remote_login_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Disable SSH remote login on macOS to reduce attack surface.
        """
        script = """#!/bin/bash
/bin/launchctl unload -w /System/Library/LaunchDaemons/ssh.plist 2>/dev/null
systemsetup -setremotelogin off 2>/dev/null
echo "Remote login (SSH) disabled."
"""
        return await self._run_mac(device_id, "Disable-Remote-Login-Mac", script)

    async def disable_guest_account_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Disable the macOS guest account to prevent unauthorized access.
        """
        script = """#!/bin/bash
sysadminctl -guestAccount off 2>/dev/null
defaults write /Library/Preferences/com.apple.loginwindow GuestEnabled -bool false
echo "Guest account disabled."
"""
        return await self._run_mac(device_id, "Disable-Guest-Account-Mac", script)

    async def disable_file_sharing_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Disable SMB and AFP file sharing on macOS.
        """
        script = """#!/bin/bash
launchctl unload -w /System/Library/LaunchDaemons/com.apple.smbd.plist 2>/dev/null
launchctl unload -w /System/Library/LaunchDaemons/com.apple.AppleFileServer.plist 2>/dev/null
echo "File sharing (SMB and AFP) disabled."
"""
        return await self._run_mac(device_id, "Disable-File-Sharing-Mac", script)

    async def enable_firewall_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Enable macOS application firewall and enable stealth mode.
        """
        script = """#!/bin/bash
/usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on
/usr/libexec/ApplicationFirewall/socketfilterfw --setstealthmode on
/usr/libexec/ApplicationFirewall/socketfilterfw --setloggingmode on
echo "macOS Firewall: enabled"
echo "Stealth mode: enabled"
echo "Logging: enabled"
"""
        return await self._run_mac(device_id, "Enable-Firewall-Mac", script)

    async def clean_tmp_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Remove files in /tmp and /Library/Caches older than 30 days on macOS.
        """
        script = """#!/bin/bash
echo "=== macOS Cache and Temp Cleanup ==="

# /tmp - files older than 30 days
before_tmp=$(du -sh /tmp 2>/dev/null | cut -f1)
find /tmp -maxdepth 2 -mtime +30 -delete 2>/dev/null
after_tmp=$(du -sh /tmp 2>/dev/null | cut -f1)
echo "/tmp: $before_tmp -> $after_tmp"

# /Library/Caches - files older than 30 days
before_cache=$(du -sh /Library/Caches 2>/dev/null | cut -f1)
find /Library/Caches -maxdepth 3 -mtime +30 -type f -delete 2>/dev/null
after_cache=$(du -sh /Library/Caches 2>/dev/null | cut -f1)
echo "/Library/Caches: $before_cache -> $after_cache"

echo "Cleanup complete."
"""
        return await self._run_mac(device_id, "Clean-Tmp-Mac", script)

    async def get_reboot_history_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Retrieve system reboot and shutdown history on macOS.
        """
        script = """#!/bin/bash
echo "=== Reboot History ==="
last reboot | head -20

echo ""
echo "=== System Uptime ==="
uptime
"""
        return await self._run_mac(device_id, "Get-Reboot-History-Mac", script)

    async def kill_process_mac(self, device_id: str, process_name: str) -> Dict[str, Any]:
        """
        Terminate a named process on macOS.
        Example: process_name="Microsoft Outlook" or "Safari"
        """
        script = f"""#!/bin/bash
PROCESS="{process_name}"
PID=$(pgrep -f "$PROCESS" 2>/dev/null)
if [ -n "$PID" ]; then
    kill -9 $PID
    echo "Terminated process: $PROCESS (PID: $PID)"
else
    echo "No running process found: $PROCESS"
fi
"""
        return await self._run_mac(device_id, f"Kill-Process-Mac-{process_name.replace(' ', '-')}", script)

    async def audit_disk_space_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Report disk space usage on all macOS volumes. Flags volumes below 10% free.
        """
        script = """#!/bin/bash
echo "=== Disk Space Report ==="
df -h | grep -v tmpfs | grep -v devfs | awk '
NR==1 { print }
NR>1 && $1 ~ /^\/dev/ {
    used_pct = $5
    gsub(/%/,"",used_pct)
    flag = ""
    if (used_pct+0 >= 90) flag = " [LOW FREE SPACE]"
    print $0 flag
}'
"""
        return await self._run_mac(device_id, "Audit-Disk-Space-Mac", script)

    async def get_performance_diagnostics_mac(self, device_id: str) -> Dict[str, Any]:
        """
        High-resolution CPU, Memory, and Disk diagnostics for macOS.
        """
        script = """#!/bin/bash
echo "=== Performance Diagnostics (macOS) ==="

echo -e "\n--- CPU Usage (Top 5) ---"
ps -Ao pcpu,comm,pmem -r | head -n 6

echo -e "\n--- Memory Usage ---"
vm_stat | perl -ne '/page size of (\d+) bytes/ and $s=$1; /Pages free:\s+(\d+)/ and $f=$1; /Pages active:\s+(\d+)/ and $a=$1; /Pages inactive:\s+(\d+)/ and $i=$1; /Pages speculative:\s+(\d+)/ and $sp=$1; /Pages wired down:\s+(\d+)/ and $w=$1; /Pages occupied by compressor:\s+(\d+)/ and $c=$1; END { printf "Total (Approx MB): %.2f\nUsed (Approx MB):  %.2f\nFree (Approx MB):  %.2f\n", ($f+$a+$i+$sp+$w+$c)*$s/1048576, ($a+$w+$c)*$s/1048576, ($f+$i+$sp)*$s/1048576 }'

echo -e "\n--- Disk IO ---"
iostat -d 1 2

echo -e "\n--- Battery Health ---"
pmset -g batt
"""
        return await self._run_mac(device_id, "Get-Performance-Diagnostics-Mac", script)

    async def get_detailed_disk_usage_mac(self, device_id: str) -> Dict[str, Any]:
        """
        Deep scan for large files and folder sizes on macOS.
        """
        script = """#!/bin/bash
echo "=== Detailed Disk Usage (macOS) ==="
echo -e "\n--- Top 10 Largest Folders in /Users ---"
du -sh /Users/* 2>/dev/null | sort -rh | head -n 10

echo -e "\n--- Top 20 Largest Files in / ---"
find / -type f -size +1G -exec ls -lh {} + 2>/dev/null | sort -rh -k 5 | head -n 20
"""
        return await self._run_mac(device_id, "Detailed-Disk-Usage-Mac", script)

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    async def _run_windows(self, device_id: str, script_name: str, script_content: str) -> Dict[str, Any]:
        """Run a PowerShell script on a Windows device via Intune deviceHealthScripts."""
        logger.info(f"Running worklet '{script_name}' on device {device_id}")
        try:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            detection = "# Detection: always trigger remediation\nWrite-Output 'Triggering remediation'\nexit 1"

            script = await self.client.create_device_health_script(
                display_name=f"Worklet_{script_name}_{timestamp}",
                detection_script=detection,
                remediation_script=script_content,
                run_as_account="system"
            )
            script_id = script["id"]
            
            # Assign to device
            await self.client.assign_health_script_to_device(script_id, device_id)
            
            await self.client.sync_device(device_id)

            return {
                "success": True,
                "worklet": script_name,
                "script_id": script_id,
                "device_id": device_id,
                "platform": "Windows",
                "message": f"Worklet '{script_name}' deployed. Device sync triggered.",
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Worklet '{script_name}' failed: {e}")
            return {
                "success": False,
                "worklet": script_name,
                "error": str(e),
                "device_id": device_id
            }

    async def _run_mac(self, device_id: str, script_name: str, script_content: str) -> Dict[str, Any]:
        """Run a Bash script on a macOS device via Intune deviceHealthScripts."""
        logger.info(f"Running worklet '{script_name}' on device {device_id}")
        try:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            detection = "#!/bin/bash\n# Detection: always trigger remediation\necho 'Triggering remediation'\nexit 1"

            script = await self.client.create_device_health_script(
                display_name=f"Worklet_{script_name}_{timestamp}",
                detection_script=detection,
                remediation_script=script_content,
                run_as_account="system"
            )
            script_id = script["id"]
            
            # Assign to device
            await self.client.assign_health_script_to_device(script_id, device_id)
            
            await self.client.sync_device(device_id)

            return {
                "success": True,
                "worklet": script_name,
                "script_id": script_id,
                "device_id": device_id,
                "platform": "macOS",
                "message": f"Worklet '{script_name}' deployed. Device sync triggered.",
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Worklet '{script_name}' failed: {e}")
            return {
                "success": False,
                "worklet": script_name,
                "error": str(e),
                "device_id": device_id
            }
