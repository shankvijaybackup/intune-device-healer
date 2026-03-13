"""
Intune Device Healer – Unified Server
Exposes:
  /mcp           – FastMCP (Model Context Protocol) endpoint
  /webhook/ticket – AtomicWork legacy webhook
  /api/v1/*      – REST API (webhook, devices, jobs, rules, auth)
  /healthz       – liveness probe
  /readyz        – readiness probe
  /metrics       – Prometheus metrics
"""

import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# ── Bootstrap: env + logging FIRST so nothing leaks to stdout before imports ──
from dotenv import load_dotenv
load_dotenv()

import structlog
# CRITICAL: send ALL logs to stderr — stdout is reserved for MCP JSON-RPC frames
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)
)

# ── Now safe to import local modules (they may log at import time) ─────────────
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, FileResponse
from starlette.staticfiles import StaticFiles
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from core.config import Config, settings
from core.auth import GraphAuthenticator
from tools.diagnostic import DiagnosticTools
from tools.windows_remediation import WindowsRemediationTools
from tools.macos_remediation import MacOSRemediationTools
from tools.automation import AutomationTools
from tools.monitoring import MonitoringTools
from tools.worklets import WorkletsTools
from tools.universal_api import UniversalApiTools
from tools.m365_mgmt import M365MgmtTools
from tools.policy_mgmt import PolicyMgmtTools
from tools.reporting_tools import ReportingTools
from tools.azure_mgmt import AzureMgmtTools
from tools.collaboration import CollaborationTools
from tools.remote_actions import RemoteActionsTools
from tools.intune_mgmt import IntuneMgmtTools
from tools.remediations import RemediationLibrary
from tools.ios_remediation import iOSRemediationTools
from tools.android_remediation import AndroidRemediationTools
from tools.lifecycle import LifecycleTools
from tools.vpn_mgmt import VPNManagement
from infra.database import init_db, close_db
from infra.metrics import registry as metrics_registry
from engine.rule_engine import get_rule_engine
from api.router import api_router
from atomicwork_webhook import app

logger = structlog.get_logger()

# Initialize MCP server
mcp = FastMCP("intune-device-healer")


# ============================================================================
# API KEY AUTH MIDDLEWARE
# Protects the /mcp endpoint — clients must send:
#   Authorization: Bearer <key>   OR   X-MCP-API-Key: <key>
# ============================================================================

class MCPAPIKeyMiddleware(BaseHTTPMiddleware):
    """Require a valid API key on every request to the MCP endpoint.

    Accepts:
        Authorization: Bearer <key>
        X-MCP-API-Key: <key>
    """

    def __init__(self, fastapi_app, api_key: str = ""):
        super().__init__(fastapi_app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next):
        # Only protect /mcp endpoints
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        # Check Authorization header (Bearer token) or X-MCP-API-Key
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        x_key = request.headers.get("X-MCP-API-Key", "").strip()

        if not self._api_key or token == self._api_key or x_key == self._api_key:
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": "Invalid or missing API key"},
        )


# Register middleware on the FastMCP server's ASGI app after server creation
# (done below after all tools are registered, see RUN SERVER section)

# Global configuration and authenticator
config = Config()
authenticator = GraphAuthenticator(config)

# Initialize tool modules
diagnostic_tools = DiagnosticTools(authenticator, config)
windows_tools = WindowsRemediationTools(authenticator, config)
macos_tools = MacOSRemediationTools(authenticator, config)
automation_tools = AutomationTools(authenticator, config)
monitoring_tools = MonitoringTools(authenticator, config)
worklets_tools = WorkletsTools(authenticator, config)
universal_api = UniversalApiTools(authenticator, config)
m365_mgmt = M365MgmtTools(authenticator, config)
policy_mgmt = PolicyMgmtTools(authenticator, config)
reporting_tools = ReportingTools(authenticator, config)
azure_mgmt = AzureMgmtTools(authenticator, config)
collaboration = CollaborationTools(authenticator, config)
remote_actions = RemoteActionsTools(authenticator, config)
intune_mgmt = IntuneMgmtTools(authenticator, config)
remediations = RemediationLibrary(authenticator, config)
ios_tools = iOSRemediationTools(authenticator, config)
android_tools = AndroidRemediationTools(authenticator, config)
lifecycle_tools = LifecycleTools(authenticator, config)
vpn_mgmt = VPNManagement(authenticator, config)


# ============================================================================
# DIAGNOSTIC TOOLS
# ============================================================================

@mcp.tool()
async def diagnose_device_comprehensive(device_id: str) -> dict:
    """
    Perform comprehensive hardware and software health diagnostics on a device.

    Args:
        device_id: Intune device ID or device name

    Returns:
        Complete diagnostic report with health score, issues, and recommendations
    """
    logger.info("diagnose_device_comprehensive", device_id=device_id)
    return await diagnostic_tools.diagnose_comprehensive(device_id)


@mcp.tool()
async def diagnose_app_crashes(device_id: str, limit: int = 10) -> dict:
    """
    Retrieve recent application crash details from Windows Event Logs.
    Useful for identifying failing binaries and crash timestamps.

    Args:
        device_id: Intune device ID or device name
        limit: Number of recent crash events to retrieve (default: 10)

    Returns:
        List of recent application errors and warnings
    """
    logger.info("diagnose_app_crashes", device_id=device_id)
    return await diagnostic_tools.diagnose_app_crashes(device_id, limit)


@mcp.tool()
async def check_hardware_health(device_id: str) -> dict:
    """
    Check hardware health: CPU temperature, disk SMART status, RAM errors.

    Args:
        device_id: Intune device ID or device name

    Returns:
        Hardware health metrics and status
    """
    logger.info("check_hardware_health", device_id=device_id)
    return await diagnostic_tools.check_hardware(device_id)


@mcp.tool()
async def check_os_health(device_id: str) -> dict:
    """
    Check OS health: system files, updates, boot configuration.

    Args:
        device_id: Intune device ID or device name

    Returns:
        Operating system health status
    """
    logger.info("check_os_health", device_id=device_id)
    return await diagnostic_tools.check_os(device_id)


@mcp.tool()
async def check_network_health(device_id: str) -> dict:
    """
    Check network health: connectivity, DNS, VPN status, proxy settings.

    Args:
        device_id: Intune device ID or device name

    Returns:
        Network connectivity and configuration status
    """
    logger.info("check_network_health", device_id=device_id)
    return await diagnostic_tools.check_network(device_id)


@mcp.tool()
async def check_security_posture(device_id: str) -> dict:
    """
    Check security posture: antivirus, firewall, encryption, compliance.

    Args:
        device_id: Intune device ID or device name

    Returns:
        Security configuration and compliance status
    """
    logger.info("check_security_posture", device_id=device_id)
    return await diagnostic_tools.check_security(device_id)


@mcp.tool()
async def check_application_health(device_id: str, app_name: str = None) -> dict:
    """
    Check application health status (Office, LOB apps, etc.).

    Args:
        device_id: Intune device ID or device name
        app_name: Optional specific application to check

    Returns:
        Application installation and health status
    """
    logger.info("check_application_health", device_id=device_id, app_name=app_name)
    return await diagnostic_tools.check_applications(device_id, app_name)


@mcp.tool()
async def predict_failures(device_id: str) -> dict:
    """
    AI-powered failure prediction based on device telemetry and trends.

    Args:
        device_id: Intune device ID or device name

    Returns:
        Predicted failures with probability scores and recommended actions
    """
    logger.info("predict_failures", device_id=device_id)
    return await diagnostic_tools.predict_failures(device_id)


# ============================================================================
# WINDOWS REMEDIATION TOOLS
# ============================================================================

@mcp.tool()
async def fix_windows_updates(device_id: str, auto_approve: bool = False) -> dict:
    """
    Fix Windows Update issues: reset components, clear cache, re-register services.

    Args:
        device_id: Windows device ID
        auto_approve: Auto-approve operation (default: False, requires manual approval)

    Returns:
        Operation result and status
    """
    logger.info("fix_windows_updates", device_id=device_id, auto_approve=auto_approve)
    return await windows_tools.fix_windows_updates(device_id, auto_approve)


@mcp.tool()
async def repair_system_files(device_id: str, auto_approve: bool = False) -> dict:
    """
    Repair Windows system files using DISM and SFC.

    Args:
        device_id: Windows device ID
        auto_approve: Auto-approve operation (Tier 2 - moderate risk)

    Returns:
        Repair results and files fixed
    """
    logger.info("repair_system_files", device_id=device_id, auto_approve=auto_approve)
    return await windows_tools.repair_system_files(device_id, auto_approve)


@mcp.tool()
async def cleanup_disk_space(device_id: str) -> dict:
    """
    Automated disk cleanup: temp files, cache, Windows.old, prefetch.
    Safe operation - executes automatically.

    Args:
        device_id: Windows device ID

    Returns:
        Space reclaimed and cleanup summary
    """
    logger.info("cleanup_disk_space", device_id=device_id)
    return await windows_tools.cleanup_disk_space(device_id)


@mcp.tool()
async def reset_network_stack(device_id: str) -> dict:
    """
    Reset Windows network stack: TCP/IP, Winsock, DNS cache.
    Safe operation - executes automatically.

    Args:
        device_id: Windows device ID

    Returns:
        Network reset status
    """
    logger.info("reset_network_stack", device_id=device_id)
    return await windows_tools.reset_network_stack(device_id)


@mcp.tool()
async def fix_vpn_configuration(device_id: str, vpn_name: str = None) -> dict:
    """
    Fix VPN configuration issues and connectivity problems.

    Args:
        device_id: Device ID
        vpn_name: Optional specific VPN connection name

    Returns:
        VPN repair status and configuration
    """
    logger.info("fix_vpn_configuration", device_id=device_id, vpn_name=vpn_name)
    return await windows_tools.fix_vpn_configuration(device_id, vpn_name)


@mcp.tool()
async def repair_outlook_pst(device_id: str, user_email: str = None) -> dict:
    """
    Scan and repair Outlook PST files using SCANPST.exe automation.

    Args:
        device_id: Windows device ID
        user_email: Optional user email to target specific profile

    Returns:
        PST repair results
    """
    logger.info("repair_outlook_pst", device_id=device_id, user_email=user_email)
    return await windows_tools.repair_outlook_pst(device_id, user_email)


@mcp.tool()
async def rebuild_outlook_profile(device_id: str, user_email: str) -> dict:
    """
    Rebuild corrupted Outlook profile and recreate OST cache.

    Args:
        device_id: Windows device ID
        user_email: User email address

    Returns:
        Profile rebuild status
    """
    logger.info("rebuild_outlook_profile", device_id=device_id, user_email=user_email)
    return await windows_tools.rebuild_outlook_profile(device_id, user_email)


@mcp.tool()
async def repair_disk_errors(device_id: str, drive_letter: str = "C", auto_approve: bool = False) -> dict:
    """
    Run CHKDSK to repair disk errors.
    Tier 3 operation - requires manual approval.

    Args:
        device_id: Windows device ID
        drive_letter: Drive letter to check (default: C)
        auto_approve: Must be explicitly set to True for execution

    Returns:
        CHKDSK results
    """
    logger.info("repair_disk_errors", device_id=device_id, drive_letter=drive_letter, auto_approve=auto_approve)
    return await windows_tools.repair_disk_errors(device_id, drive_letter, auto_approve)


@mcp.tool()
async def enable_bitlocker(device_id: str, recovery_key_location: str = "azure_ad") -> dict:
    """
    Enable or repair BitLocker encryption.

    Args:
        device_id: Windows device ID
        recovery_key_location: Where to store recovery key (azure_ad, file)

    Returns:
        BitLocker status and recovery key info
    """
    logger.info("enable_bitlocker", device_id=device_id)
    return await windows_tools.enable_bitlocker(device_id, recovery_key_location)


@mcp.tool()
async def update_drivers_auto(device_id: str, driver_category: str = "all") -> dict:
    """
    Automatically update device drivers via Windows Update.

    Args:
        device_id: Windows device ID
        driver_category: Driver category (all, network, audio, display)

    Returns:
        Driver update results
    """
    logger.info("update_drivers_auto", device_id=device_id, driver_category=driver_category)
    return await windows_tools.update_drivers_auto(device_id, driver_category)


# ============================================================================
# MACOS REMEDIATION TOOLS
# ============================================================================

@mcp.tool()
async def reset_smc(device_id: str) -> dict:
    """
    Reset System Management Controller on Mac.
    Safe operation for fixing power, thermal, battery issues.

    Args:
        device_id: macOS device ID

    Returns:
        SMC reset status
    """
    logger.info("reset_smc", device_id=device_id)
    return await macos_tools.reset_smc(device_id)


@mcp.tool()
async def reset_nvram(device_id: str) -> dict:
    """
    Reset NVRAM/PRAM on Mac.
    Safe operation for fixing boot, display, sound issues.

    Args:
        device_id: macOS device ID

    Returns:
        NVRAM reset status
    """
    logger.info("reset_nvram", device_id=device_id)
    return await macos_tools.reset_nvram(device_id)


@mcp.tool()
async def repair_disk_permissions_mac(device_id: str) -> dict:
    """
    Repair disk permissions on macOS.

    Args:
        device_id: macOS device ID

    Returns:
        Permission repair results
    """
    logger.info("repair_disk_permissions_mac", device_id=device_id)
    return await macos_tools.repair_disk_permissions(device_id)


@mcp.tool()
async def fix_spotlight_index(device_id: str) -> dict:
    """
    Rebuild Spotlight search index on macOS.

    Args:
        device_id: macOS device ID

    Returns:
        Spotlight rebuild status
    """
    logger.info("fix_spotlight_index", device_id=device_id)
    return await macos_tools.fix_spotlight_index(device_id)


@mcp.tool()
async def reset_network_settings_mac(device_id: str) -> dict:
    """
    Reset all network settings on macOS.

    Args:
        device_id: macOS device ID

    Returns:
        Network reset status
    """
    logger.info("reset_network_settings_mac", device_id=device_id)
    return await macos_tools.reset_network_settings(device_id)


@mcp.tool()
async def fix_vpn_profile_mac(device_id: str, vpn_name: str = None) -> dict:
    """
    Fix VPN configuration on macOS.

    Args:
        device_id: macOS device ID
        vpn_name: Optional VPN connection name

    Returns:
        VPN repair status
    """
    logger.info("fix_vpn_profile_mac", device_id=device_id, vpn_name=vpn_name)
    return await macos_tools.fix_vpn_profile(device_id, vpn_name)


@mcp.tool()
async def fix_outlook_mac(device_id: str, user_email: str = None) -> dict:
    """
    Fix Outlook for Mac issues: profile, cache, database.

    Args:
        device_id: macOS device ID
        user_email: Optional user email

    Returns:
        Outlook repair status
    """
    logger.info("fix_outlook_mac", device_id=device_id, user_email=user_email)
    return await macos_tools.fix_outlook_mac(device_id, user_email)


# ============================================================================
# AUTOMATION TOOLS
# ============================================================================

@mcp.tool()
async def auto_heal_device(
    device_id: str,
    auto_approve_safe_fixes: bool = True,
    issues_to_fix: list = None
) -> dict:
    """
    Automatically diagnose and fix all detected issues on a device.

    Args:
        device_id: Device ID
        auto_approve_safe_fixes: Auto-approve Tier 1 fixes (default: True)
        issues_to_fix: Optional list of specific issues to fix (if None, fixes all)

    Returns:
        Complete healing report with before/after health scores
    """
    logger.info("auto_heal_device", device_id=device_id, auto_approve_safe_fixes=auto_approve_safe_fixes)
    return await automation_tools.auto_heal_device(device_id, auto_approve_safe_fixes, issues_to_fix)


@mcp.tool()
async def bulk_heal_devices(
    device_ids: list,
    fix_types: list = None,
    max_concurrent: int = 5
) -> dict:
    """
    Heal multiple devices simultaneously.

    Args:
        device_ids: List of device IDs
        fix_types: Optional list of fix types to apply (e.g., ["vpn", "disk", "outlook"])
        max_concurrent: Maximum concurrent operations (default: 5)

    Returns:
        Bulk operation results
    """
    logger.info("bulk_heal_devices", device_count=len(device_ids), fix_types=fix_types)
    return await automation_tools.bulk_heal_devices(device_ids, fix_types, max_concurrent)


@mcp.tool()
async def deploy_remediation_script(
    name: str,
    detection_script: str,
    remediation_script: str,
    platform: str,
    target_devices: list = None,
    target_groups: list = None,
    schedule: str = "manual"
) -> dict:
    """
    Deploy custom proactive remediation script to devices.

    Args:
        name: Script name
        detection_script: PowerShell/Shell detection script
        remediation_script: PowerShell/Shell remediation script
        platform: windows or macos
        target_devices: Optional list of device IDs
        target_groups: Optional list of group names
        schedule: Execution schedule (manual, hourly, daily, weekly)

    Returns:
        Script deployment status and ID
    """
    logger.info("deploy_remediation_script", name=name, platform=platform, schedule=schedule)
    return await automation_tools.deploy_remediation_script(
        name, detection_script, remediation_script, platform,
        target_devices, target_groups, schedule
    )


@mcp.tool()
async def schedule_maintenance(
    device_id: str,
    maintenance_tasks: list,
    schedule_time: str,
    recurrence: str = "once"
) -> dict:
    """
    Schedule device maintenance tasks.

    Args:
        device_id: Device ID
        maintenance_tasks: List of maintenance operations
        schedule_time: ISO 8601 datetime or cron expression
        recurrence: once, daily, weekly, monthly

    Returns:
        Scheduled maintenance job ID
    """
    logger.info("schedule_maintenance", device_id=device_id, schedule_time=schedule_time)
    return await automation_tools.schedule_maintenance(device_id, maintenance_tasks, schedule_time, recurrence)


# ============================================================================
# MONITORING TOOLS
# ============================================================================

@mcp.tool()
async def get_fleet_health_dashboard() -> dict:
    """
    Get real-time health dashboard for entire device fleet.

    Returns:
        Fleet health metrics, top issues, devices needing attention
    """
    logger.info("get_fleet_health_dashboard")
    return await monitoring_tools.get_fleet_health_dashboard()


@mcp.tool()
async def get_device_health_score(device_id: str) -> dict:
    """
    Calculate comprehensive health score (0-100) for a device.

    Args:
        device_id: Device ID

    Returns:
        Health score with breakdown by category
    """
    logger.info("get_device_health_score", device_id=device_id)
    return await monitoring_tools.get_device_health_score(device_id)


@mcp.tool()
async def get_remediation_history(device_id: str = None, days: int = 7) -> dict:
    """
    Get remediation history for device(s).

    Args:
        device_id: Optional device ID (if None, returns all devices)
        days: Number of days to look back (default: 7)

    Returns:
        Remediation operation history
    """
    logger.info("get_remediation_history", device_id=device_id, days=days)
    return await monitoring_tools.get_remediation_history(device_id, days)


@mcp.tool()
async def export_health_report(
    format: str = "excel",
    include_devices: list = None,
    report_type: str = "comprehensive"
) -> dict:
    """
    Export device health report.

    Args:
        format: excel or pdf
        include_devices: Optional list of device IDs (if None, includes all)
        report_type: comprehensive, summary, or compliance

    Returns:
        Report file path and download URL
    """
    logger.info("export_health_report", format=format, report_type=report_type)
    return await monitoring_tools.export_health_report(format, include_devices, report_type)


@mcp.tool()
async def scan_for_issues(issue_type: str = "all", severity: str = "all") -> dict:
    """
    Scan entire fleet for specific types of issues.

    Args:
        issue_type: all, vpn, disk, network, outlook, security, performance
        severity: all, critical, high, medium, low

    Returns:
        List of devices with matching issues
    """
    logger.info("scan_for_issues", issue_type=issue_type, severity=severity)
    return await monitoring_tools.scan_for_issues(issue_type, severity)


# ============================================================================
# ADDITIONAL UTILITY TOOLS
# ============================================================================

@mcp.tool()
async def list_intune_devices(
    platform: str = "all",
    compliance_state: str = "all",
    limit: int = 100
) -> dict:
    """
    List all Intune-managed devices.

    Args:
        platform: all, windows, macos, ios, android
        compliance_state: all, compliant, noncompliant, unknown
        limit: Maximum number of devices to return

    Returns:
        List of devices with basic info
    """
    logger.info("list_intune_devices", platform=platform, compliance_state=compliance_state)
    return await diagnostic_tools.list_devices(platform, compliance_state, limit)


@mcp.tool()
async def sync_device(device_id: str, wait_for_completion: bool = True) -> dict:
    """
    Trigger immediate Intune sync for a device.

    Args:
        device_id: Device ID
        wait_for_completion: Wait for sync to complete (default: True)

    Returns:
        Sync status and last sync time
    """
    logger.info("sync_device", device_id=device_id, wait_for_completion=wait_for_completion)
    return await automation_tools.sync_device(device_id, wait_for_completion)


@mcp.tool()
async def get_device_logs(device_id: str, log_type: str = "all", hours: int = 24) -> dict:
    """
    Retrieve device logs from Intune.

    Args:
        device_id: Device ID
        log_type: all, compliance, configuration, app_install
        hours: Hours of logs to retrieve

    Returns:
        Device logs
    """
    logger.info("get_device_logs", device_id=device_id, log_type=log_type)
    return await monitoring_tools.get_device_logs(device_id, log_type, hours)


# ============================================================================
# WORKLETS — SECURITY, DIAGNOSTICS, MAINTENANCE
# ============================================================================

@mcp.tool()
async def worklet_disable_smb_v1(device_id: str) -> dict:
    """Disable SMBv1 on Windows. Removes EternalBlue/WannaCry attack surface."""
    return await worklets_tools.disable_smb_v1(device_id)

@mcp.tool()
async def worklet_enable_windows_firewall(device_id: str) -> dict:
    """Enable Windows Firewall across Domain, Public, and Private profiles."""
    return await worklets_tools.enable_windows_firewall(device_id)

@mcp.tool()
async def worklet_disable_rdp(device_id: str) -> dict:
    """Disable Remote Desktop Protocol on Windows to reduce attack surface."""
    return await worklets_tools.disable_rdp(device_id)

@mcp.tool()
async def worklet_disable_usb_storage_windows(device_id: str) -> dict:
    """Block USB removable storage on Windows via registry policy."""
    return await worklets_tools.disable_usb_storage_windows(device_id)

@mcp.tool()
async def worklet_enforce_lock_screen_windows(device_id: str, idle_minutes: int = 10) -> dict:
    """Enforce automatic lock screen after inactivity on Windows. Default: 10 minutes."""
    return await worklets_tools.enforce_lock_screen_windows(device_id, idle_minutes)

@mcp.tool()
async def worklet_disable_powershell_v2(device_id: str) -> dict:
    """Disable PowerShell v2 on Windows to prevent security control bypass."""
    return await worklets_tools.disable_powershell_v2(device_id)

@mcp.tool()
async def worklet_disable_llmnr_windows(device_id: str) -> dict:
    """Disable LLMNR on Windows. Prevents responder/man-in-the-middle attacks."""
    return await worklets_tools.disable_llmnr_windows(device_id)

@mcp.tool()
async def worklet_force_password_reset(device_id: str) -> dict:
    """Require all local user accounts to reset password at next logon."""
    return await worklets_tools.force_password_reset_on_logon(device_id)

@mcp.tool()
async def worklet_disable_netbios(device_id: str) -> dict:
    """Disable NetBIOS over TCP/IP on all Windows network adapters."""
    return await worklets_tools.disable_netbios(device_id)

@mcp.tool()
async def worklet_get_event_log_errors(device_id: str, hours: int = 24) -> dict:
    """Get System and Application event log errors from Windows for the last N hours."""
    return await worklets_tools.get_event_log_errors(device_id, hours)

@mcp.tool()
async def worklet_get_reboot_history_windows(device_id: str) -> dict:
    """Get last 10 reboot events and current uptime from Windows."""
    return await worklets_tools.get_reboot_history_windows(device_id)

@mcp.tool()
async def worklet_get_disk_space_report(device_id: str) -> dict:
    """Report free disk space on all Windows drives. Flags drives below 10% free."""
    return await worklets_tools.get_disk_space_report(device_id)

@mcp.tool()
async def worklet_get_battery_health(device_id: str) -> dict:
    """Check battery health, charge status and generate power report on Windows laptops."""
    return await worklets_tools.get_battery_health_windows(device_id)

@mcp.tool()
async def worklet_audit_local_admins(device_id: str) -> dict:
    """List all local administrator accounts on a Windows device. Security audit."""
    return await worklets_tools.audit_local_admin_accounts(device_id)

@mcp.tool()
async def worklet_get_browser_extensions(device_id: str) -> dict:
    """List all installed browser extensions across Chrome, Edge, Firefox, Brave on Windows."""
    return await worklets_tools.get_browser_extensions(device_id)

@mcp.tool()
async def worklet_remove_old_user_profiles(device_id: str, older_than_days: int = 90) -> dict:
    """Delete Windows user profiles not used in N days. Default: 90 days."""
    return await worklets_tools.remove_old_user_profiles(device_id, older_than_days)

@mcp.tool()
async def worklet_clean_temp_files_all_users(device_id: str) -> dict:
    """Remove temp files from all user profiles and system temp on Windows."""
    return await worklets_tools.clean_temp_files_all_users(device_id)

@mcp.tool()
async def worklet_remove_windows_bloatware(device_id: str) -> dict:
    """Remove pre-installed Windows Store bloatware (Xbox, Candy Crush, Bing apps, etc.)."""
    return await worklets_tools.remove_windows_bloatware(device_id)

@mcp.tool()
async def worklet_kill_process_windows(device_id: str, process_name: str) -> dict:
    """Terminate a named process on Windows. Args: process_name e.g. 'outlook' or 'chrome'."""
    return await worklets_tools.kill_process_windows(device_id, process_name)

@mcp.tool()
async def worklet_get_windows_update_events(device_id: str) -> dict:
    """Extract recent Windows Update events for the last 30 days."""
    return await worklets_tools.get_windows_update_events(device_id)

@mcp.tool()
async def worklet_disable_usb_storage_mac(device_id: str) -> dict:
    """Disable USB mass storage on macOS by unloading the IOUSBMassStorageClass kext."""
    return await worklets_tools.disable_usb_storage_mac(device_id)

@mcp.tool()
async def worklet_disable_bluetooth_mac(device_id: str) -> dict:
    """Disable Bluetooth on macOS."""
    return await worklets_tools.disable_bluetooth_mac(device_id)

@mcp.tool()
async def worklet_enforce_lock_screen_mac(device_id: str, idle_minutes: int = 10) -> dict:
    """Enforce automatic screen lock after inactivity on macOS. Default: 10 minutes."""
    return await worklets_tools.enforce_lock_screen_mac(device_id, idle_minutes)

@mcp.tool()
async def worklet_disable_remote_login_mac(device_id: str) -> dict:
    """Disable SSH remote login on macOS."""
    return await worklets_tools.disable_remote_login_mac(device_id)

@mcp.tool()
async def worklet_disable_guest_account_mac(device_id: str) -> dict:
    """Disable the macOS guest account."""
    return await worklets_tools.disable_guest_account_mac(device_id)

@mcp.tool()
async def worklet_disable_file_sharing_mac(device_id: str) -> dict:
    """Disable SMB and AFP file sharing on macOS."""
    return await worklets_tools.disable_file_sharing_mac(device_id)

@mcp.tool()
async def worklet_enable_firewall_mac(device_id: str) -> dict:
    """Enable macOS application firewall with stealth mode and logging."""
    return await worklets_tools.enable_firewall_mac(device_id)

@mcp.tool()
async def worklet_clean_tmp_mac(device_id: str) -> dict:
    """Remove /tmp and /Library/Caches files older than 30 days on macOS."""
    return await worklets_tools.clean_tmp_mac(device_id)

@mcp.tool()
async def worklet_get_reboot_history_mac(device_id: str) -> dict:
    """Get reboot history and current uptime from macOS."""
    return await worklets_tools.get_reboot_history_mac(device_id)

@mcp.tool()
async def worklet_kill_process_mac(device_id: str, process_name: str) -> dict:
    """Terminate a named process on macOS. Args: process_name e.g. 'Microsoft Outlook'."""
    return await worklets_tools.kill_process_mac(device_id, process_name)

@mcp.tool()
async def worklet_audit_disk_space_mac(device_id: str) -> dict:
    """Report disk space on all macOS volumes. Flags volumes above 90% used."""
    return await worklets_tools.audit_disk_space_mac(device_id)


# ============================================================================
# STARTUP / SHUTDOWN  (FR-10: graceful drain)
# ============================================================================

_shutting_down = False


def _handle_sigterm(*_):
    global _shutting_down
    _shutting_down = True
    logger.info("SIGTERM received – initiating graceful shutdown")


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


@app.on_event("startup")
async def _startup():
    # Initialise database tables (non-fatal — MCP tools work without DB)
    try:
        await init_db()
        logger.info("Database initialised")
    except Exception as exc:
        logger.warning("Database unavailable – REST API features disabled", error=str(exc))

    # Load rules from YAML
    engine = get_rule_engine()
    rules_path = settings.rules_config_path
    # Fallback: look for rules.yaml next to this file or in /config/
    if not Path(rules_path).exists():
        fallback = Path(__file__).parent.parent / "config" / "rules.yaml"
        if fallback.exists():
            rules_path = str(fallback)
    n = engine.load_from_file(rules_path)
    logger.info("Rules loaded", count=n, path=rules_path)


@app.on_event("shutdown")
async def _shutdown():
    await close_db()
    logger.info("Database connection pool closed")


# ============================================================================
# HEALTH & METRICS  (FR-9)
# ============================================================================

@app.get("/healthz", tags=["ops"])
async def healthz():
    return PlainTextResponse("ok")


@app.get("/readyz", tags=["ops"])
async def readyz():
    if _shutting_down:
        return JSONResponse(status_code=503, content={"status": "shutting_down"})
    return JSONResponse({"status": "ready"})


@app.get("/metrics", tags=["ops"])
async def metrics():
    data = generate_latest(metrics_registry)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# MOUNT: REST API + MCP
# ============================================================================

# REST API router (auth, webhook, devices, jobs, rules)
app.include_router(api_router)

# MCP API-key middleware + mount
_api_key = os.environ.get("MCP_API_KEY", "")
app.add_middleware(MCPAPIKeyMiddleware, api_key=_api_key)
app.mount("/mcp", mcp.http_app(stateless_http=True))

# ── Static Files & Dashboard (FR-11) ───────────────────────────────────────
# Place these last so they don't shadow API routes
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # If it looks like an API or health check, let it 404 naturally if not matched above
        if full_path.startswith(("api/", "webhook/", "mcp", "healthz", "metrics", "readyz")):
            raise HTTPException(status_code=404)
        
        # Otherwise serve index.html for SPA routing
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return PlainTextResponse("Frontend build missing", status_code=404)
else:
    logger.warning("Frontend 'dist' directory not found. Dashboard UI will be unavailable.")


# ============================================================================
# RUN SERVER
# ============================================================================


# ============================================================================
# UNIVERSAL API & GRAPH ADVANCED TOOLS
# ============================================================================

@mcp.tool()
async def call_microsoft_api(
    api_type: str,
    path: str,
    method: str = "GET",
    api_version: str = None,
    subscription_id: str = None,
    query_params: dict = None,
    body: dict = None,
    graph_api_version: str = "v1.0",
    fetch_all: bool = False
) -> dict:
    """Execute direct API calls to Microsoft Graph or Azure Resource Management."""
    return await universal_api.call_microsoft_api(
        api_type, path, method, api_version, subscription_id, 
        query_params, body, graph_api_version, fetch_all
    )

@mcp.tool()
async def execute_graph_batch(requests: list) -> dict:
    """Execute multiple Graph API requests in one batch (JSON batching)."""
    return await universal_api.execute_graph_batch(requests)

@mcp.tool()
async def execute_delta_query(resource: str, delta_token: str = None) -> dict:
    """Track incremental changes via delta query."""
    return await universal_api.execute_delta_query(resource, delta_token)

# ============================================================================
# M365 MANAGEMENT TOOLS
# ============================================================================

@mcp.tool()
async def list_users(filter: str = None, top: int = 100) -> dict:
    """List users in the tenant with optional OData filter."""
    return await m365_mgmt.list_users(filter=filter, top=top)

@mcp.tool()
async def get_user_info(user_id: str) -> dict:
    """Get detailed information for a specific user."""
    return await m365_mgmt.get_user_info(user_id)

@mcp.tool()
async def list_groups(filter: str = None, top: int = 100) -> dict:
    """List groups in the tenant."""
    return await m365_mgmt.list_groups(filter=filter, top=top)

@mcp.tool()
async def manage_group_membership(group_id: str, member_id: str, action: str = "add") -> dict:
    """Add or remove a member from a group (action: 'add' or 'remove')."""
    return await m365_mgmt.manage_group_membership(group_id, member_id, action)

# ============================================================================
# POLICY & SECURITY TOOLS
# ============================================================================

@mcp.tool()
async def list_conditional_access_policies() -> dict:
    """List all Microsoft Entra ID Conditional Access policies."""
    return await policy_mgmt.list_conditional_access_policies()

@mcp.tool()
async def list_intune_compliance_policies() -> dict:
    """List all Intune device compliance policies across platforms."""
    return await policy_mgmt.list_intune_compliance_policies()

@mcp.tool()
async def list_intune_configuration_profiles() -> dict:
    """List all Intune device configuration profiles."""
    return await policy_mgmt.list_intune_configuration_profiles()

@mcp.tool()
async def backup_all_policies() -> dict:
    """Export a summary backup of CA, compliance, and configuration policies."""
    return await policy_mgmt.backup_policies(policy_types=["all"])

# ============================================================================
# ADVANCED REPORTING TOOLS
# ============================================================================

@mcp.tool()
async def generate_professional_health_report(format: str = "docx") -> dict:
    """Generate a professional docx or xlsx report of fleet health."""
    return await reporting_tools.generate_fleet_health_report(format=format)


# ============================================================================
# INTELLIGENT PROMPTS
# ============================================================================

@mcp.prompt()
def security_audit_prompt() -> str:
    """Analyze the current security posture of the tenant."""
    return (
        "Perform a comprehensive security audit of this tenant. "
        "1. List all Conditional Access policies and identify any that are disabled or too permissive. "
        "2. Check Intune compliance policies for all platforms. "
        "3. List all users with local admin rights using the 'worklet_audit_local_admins' tool on a sample of devices. "
        "4. Summarize the findings and suggest improvements."
    )

@mcp.prompt()
def fleet_health_analysis_prompt() -> str:
    """Analyze the overall health of the device fleet."""
    return (
        "Generate a complete fleet health analysis. "
        "1. Get the current fleet health dashboard metrics. "
        "2. identify top reaching issues. "
        "3. Generate a professional Word report (.docx) summarizing these findings. "
        "4. Provide the path to the generated report."
    )

@mcp.prompt()
def user_onboarding_check_prompt(user_id: str) -> str:
    """Check if a user is correctly set up in M365 and Intune."""
    return (
        f"Verify the onboarding status for user '{user_id}'. "
        f"1. Get user details and groups. "
        f"2. Check user's MFA registration status. "
        f"3. List devices associated with this user. "
        f"4. Confirm if the user is a member of any critical security groups."
    )

# ============================================================================
# AZURE MANAGEMENT TOOLS (DevOps & Finance)
# ============================================================================

@mcp.tool()
async def get_azure_subscription_overview(subscription_id: str = None) -> dict:
    """Get a high-level inventory of all resources in an Azure subscription."""
    return await azure_mgmt.get_subscription_overview(subscription_id)

@mcp.tool()
async def get_azure_cost_analysis(subscription_id: str = None, timeframe: str = "BillingMonthToDate") -> dict:
    """Get detailed Azure cost analysis and spending forecast."""
    return await azure_mgmt.get_cost_analysis(subscription_id, timeframe)

# ============================================================================
# COLLABORATION TOOLS (SharePoint & Teams)
# ============================================================================

@mcp.tool()
async def create_sharepoint_site(display_name: str, alias: str, description: str = "") -> dict:
    """Create a new SharePoint site and associated M365 group."""
    return await collaboration.create_sharepoint_site(display_name, alias, description)

@mcp.tool()
async def manage_teams_channel(team_id: str, channel_name: str, action: str = "create") -> dict:
    """Create or list channels within a Microsoft Team."""
    return await collaboration.manage_teams_channel(team_id, channel_name, action=action)

# ============================================================================
# AGENTIC MISSION PROMPTS
# ============================================================================

@mcp.prompt()
def project_phoenix_starter_prompt(project_name: str, lead_user_id: str) -> str:
    """Mission: Set up a complete collaboration environment for a new project."""
    return (
        f"Initialize the collaboration environment for project '{project_name}'. "
        f"1. Create a SharePoint site named '{project_name}'. "
        f"2. Add the lead user '{lead_user_id}' as a member of the project group. "
        f"3. Create a record of this setup in a new Word document using the reporting tools. "
        f"4. Output the final site URL and status."
    )

@mcp.prompt()
def monthly_cost_audit_mission_prompt() -> str:
    """Mission: Perform a comprehensive Azure cost audit and report."""
    return (
        "Execute a monthly Azure cost audit. "
        "1. Fetch the actual cost analysis for the current billing period. "
        "2. Identify the top 3 most expensive resource groups. "
        "3. Generate an Excel report (.xlsx) with a breakdown of daily costs. "
        "4. Highlight any abnormal spending patterns compared to the forecast."
    )

# ============================================================================
# REMOTE DEVICE ACTIONS (Intune Native)
# ============================================================================

@mcp.tool()
async def reboot_intune_device(device_id: str) -> dict:
    """Restart a managed device remotely via Intune."""
    return await remote_actions.reboot_device(device_id)

@mcp.tool()
async def lock_intune_device(device_id: str) -> dict:
    """Lock a managed device remotely (Windows, macOS, Mobile)."""
    return await remote_actions.lock_device(device_id)

@mcp.tool()
async def wipe_intune_device(device_id: str, keep_enrollment: bool = False) -> dict:
    """Perform a factory reset (wipe) on a managed device."""
    return await remote_actions.wipe_device(device_id, keep_enrollment)

@mcp.tool()
async def trigger_defender_scan(device_id: str, full_scan: bool = False) -> dict:
    """Trigger a Microsoft Defender virus scan on a Windows device."""
    if full_scan:
        return await remote_actions.full_scan_defender(device_id)
    return await remote_actions.quick_scan_defender(device_id)

@mcp.tool()
async def sync_intune_device(device_id: str) -> dict:
    """Force a device to check-in/sync with Intune immediately."""
    return await remote_actions.sync_device(device_id)

# ============================================================================
# AGENTIC TROUBLESHOOTING PROMPTS
# ============================================================================

@mcp.prompt()
def remote_troubleshooting_mission_prompt(device_id: str, symptom: str) -> str:
    """Mission: Autonomously diagnose and fix a device issue."""
    return (
        f"A device ({device_id}) is reporting the following symptom: '{symptom}'. "
        "Your mission is to: "
        "1. Get device details and check its current compliance status. "
        "2. Run relevant diagnostics (e.g., check disk space, reboot history, or event logs). "
        "3. Based on the findings, select and execute the most appropriate remediation tool (Worklet or Remote Action). "
        "4. Verify the fix if possible and provide a summary of your actions."
    )

@mcp.prompt()
def proactive_security_hardening_prompt(device_id: str) -> str:
    """Mission: Harden a device's security posture."""
    return (
        f"Perform a proactive security hardening on device '{device_id}'. "
        "1. Enable Windows Firewall if disabled. "
        "2. Disable legacy protocols like SMBv1 and LLMNR. "
        "3. Audit local administrator accounts. "
        "4. Trigger a Defender quick scan. "
        "5. Document all changes in a health report."
    )

# ============================================================================
# ADVANCED INTUNE MANAGEMENT (Helpdesk & Autopilot)
# ============================================================================

@mcp.tool()
async def get_bitlocker_recovery_key(device_id: str) -> dict:
    """Retrieve BitLocker recovery keys for a Windows device (Requires Admin)."""
    return await intune_mgmt.get_bitlocker_recovery_key(device_id)

@mcp.tool()
async def list_autopilot_devices() -> list:
    """List all devices registered in the Windows Autopilot service."""
    return await intune_mgmt.list_autopilot_devices()

@mcp.tool()
async def sync_autopilot() -> dict:
    """Trigger a manual sync of Autopilot device identities."""
    return await intune_mgmt.sync_autopilot()

@mcp.tool()
async def list_managed_apps(platform: str = None) -> list:
    """List all mobile and desktop apps managed by Intune."""
    return await intune_mgmt.list_mobile_apps(platform)

@mcp.tool()
async def get_device_hardware_specs(device_id: str) -> dict:
    """Get detailed hardware specs (CPU, RAM, Storage, SN) for a device."""
    return await intune_mgmt.get_device_hardware_inventory(device_id)

@mcp.tool()
async def set_device_primary_user(device_id: str, user_id: str) -> dict:
    """Assign or change the primary user for a managed device."""
    return await intune_mgmt.set_primary_user(device_id, user_id)

# ============================================================================
# ADVANCED INTUNE MISSION PROMPTS
# ============================================================================

@mcp.prompt()
def device_forensics_mission_prompt(device_id: str) -> str:
    """Mission: Complete diagnostic and security profile of a device."""
    return (
        f"Perform a deep forensic analysis of device '{device_id}'. "
        "1. Get hardware specs and disk space status. "
        "2. Retrieve BitLocker recovery keys for emergency access. "
        "3. Check for any compliance violations or configuration errors. "
        "4. Summarize the complete device state and health."
    )

@mcp.prompt()
def autopilot_provisioning_check_prompt() -> str:
    """Mission: Verify Autopilot health and sync status."""
    return (
        "Check the state of Windows Autopilot deployment. "
        "1. List registered Autopilot devices. "
        "2. Trigger a sync to ensure the inventory is up to date. "
        "3. Identify any devices without an assigned profile."
    )

# ============================================================================
# PERFORMANCE & DEEP DIAGNOSTICS
# ============================================================================

@mcp.tool()
async def get_performance_diagnostics(device_id: str) -> dict:
    """Get high-resolution CPU, Memory, and Disk stats for a device."""
    # Detect platform from device details or assume based on ID lookup
    device = await device_diagnostics.client.get_device(device_id)
    platform = device.get("operatingSystem", "Unknown")
    
    if "Windows" in platform:
        return await worklets.get_performance_diagnostics_windows(device_id)
    else:
        return await worklets.get_performance_diagnostics_mac(device_id)

@mcp.tool()
async def fix_printer_spooler(device_id: str) -> dict:
    """Fix stuck print jobs and spooler crashes on Windows."""
    return await worklets.fix_printer_spooler(device_id)

@mcp.tool()
async def get_detailed_disk_usage(device_id: str) -> dict:
    """Deep scan for large files and folder sizes."""
    device = await device_diagnostics.client.get_device(device_id)
    platform = device.get("operatingSystem", "Unknown")
    
    if "Windows" in platform:
        return await worklets.get_detailed_disk_usage_windows(device_id)
    else:
        return await worklets.get_detailed_disk_usage_mac(device_id)

# ============================================================================
# DEEP DIAGNOSTICS MISSION PROMPTS
# ============================================================================

@mcp.prompt()
def performance_investigation_mission_prompt(device_id: str) -> str:
    """Mission: Investigate and resolve performance slowdowns."""
    return (
        f"A user is reporting performance issues on device '{device_id}'. "
        "Your mission is to: "
        "1. Capture high-resolution performance diagnostics (CPU, Mem, IO). "
        "2. Identify top resource-consuming processes. "
        "3. Check for low disk space and identify large files/folders. "
        "4. If a specific process is runaway, consider killing it. "
        "5. If disk is full, run cleanup tools. "
        "6. Provide a report on what was slowing down the system and what you did to fix it."
    )

@mcp.prompt()
def printer_troubleshooting_mission_prompt(device_id: str) -> str:
    """Mission: Fix printing issues on a device."""
    return (
        f"A user is unable to print from device '{device_id}'. "
        "1. Run the Print Spooler fix tool. "
        "2. Check event logs for printer-related errors. "
        "3. Verify if the Spooler service is running. "
        "4. Report the status to the user."
    )

# ============================================================================
# PERFORMANCE & DEEP DIAGNOSTICS
# ============================================================================

@mcp.tool()
async def get_realtime_performance_stats(device_id: str) -> dict:
    """
    Get near-real-time CPU, Memory, and Top Processes for a device.
    Triggered via an immediate MDM push.
    """
    return await worklets_tools.run_performance_probe(device_id)

@mcp.tool()
async def trigger_cpu_stress(device_id: str, duration_seconds: int = 60) -> dict:
    """
    [SIMULATION] Spike CPU on a Windows device for a fixed duration.
    Used for validating 'Auto-Heal' and Real-Time performance stats.

    Args:
        device_id: Device ID
        duration_seconds: Duration of the spike in seconds (default: 60)

    Returns:
        Simulation deployment status
    """
    logger.info("trigger_cpu_stress", device_id=device_id, duration_seconds=duration_seconds)
    return await worklets_tools.trigger_cpu_stress(device_id, duration_seconds)

@mcp.tool()
async def remediate_low_disk_space(device_id: str) -> dict:
    """Trigger an automated disk cleanup and notification on a device."""
    return await remediations.deploy_disk_cleanup(device_id)

@mcp.tool()
async def remediate_printer_spooler(device_id: str) -> dict:
    """Fix stuck print jobs and restart the Spooler service in real-time."""
    return await remediations.deploy_printer_spooler_fix(device_id)

@mcp.tool()
async def remediate_high_uptime(device_id: str) -> dict:
    """Prompt user for reboot or force restart if uptime > 7 days."""
    return await remediations.deploy_high_uptime_reboot(device_id)

# ============================================================================
# VPN MANAGEMENT TOOLS
# ============================================================================

@mcp.tool()
async def audit_vpn_health(device_id: str) -> dict:
    """Check VPN adapter status, driver health, and profile configuration."""
    return await vpn_mgmt.check_vpn_health(device_id)

@mcp.tool()
async def audit_vpn_health_mac(device_id: str) -> dict:
    """Audit VPN configuration on macOS devices."""
    return await vpn_mgmt.check_vpn_health_mac(device_id)

@mcp.tool()
async def install_vpn_client(device_id: str, client_type: str = "AnyConnect") -> dict:
    """Trigger a silent installation of a VPN client (AnyConnect, GlobalProtect, etc.)."""
    return await vpn_mgmt.install_vpn_client(device_id, client_type)

@mcp.tool()
async def get_realtime_vpn_stats(device_id: str) -> dict:
    """Get live bytes sent/received and connection duration for active VPN."""
    return await vpn_mgmt.get_realtime_vpn_stats(device_id)

@mcp.tool()
async def get_cloudflare_warp_status(device_id: str) -> dict:
    """Get Cloudflare WARP specific status, settings, and connectivity stats."""
    return await vpn_mgmt.get_warp_status(device_id)

@mcp.tool()
async def get_cloudflare_warp_status_mac(device_id: str) -> dict:
    """Get Cloudflare WARP specific status on macOS."""
    return await vpn_mgmt.get_warp_status_mac(device_id)

@mcp.tool()
async def auto_remediate_from_context(subject: str, description: str, device_id: str) -> dict:
    """
    Intelligently analyze ticket context and perform best-fit remediation actions.
    Automatically maps issues like "CPU slow" or "Printer stuck" to the correct tools.
    """
    from atomicwork_webhook import TicketAnalyzer, run_remediation
    
    # 1. Detect platform
    device = await diagnostic_tools.client.get_device(device_id)
    platform = device.get("operatingSystem", "Windows")
    
    # 2. Analyze context
    analysis = TicketAnalyzer.analyze(subject, description, platform)
    
    # 3. Execute remediation
    result = await run_remediation(device_id, analysis["actions"], platform)
    
    return {
        "analysis": analysis,
        "remediation_result": result,
        "summary": f"Detected '{analysis['issue_type']}' and executed {len(result['executed'])} actions."
    }


# ============================================================================
# iOS / iPadOS REMEDIATION TOOLS  (Issues 78-84 + helpers)
# ============================================================================

@mcp.tool()
async def fix_enrollment_ios(device_id: str) -> dict:
    """
    Recover a stalled or failed iOS/iPadOS ADE enrollment.
    Triggers ADE sync and forces device check-in.

    Args:
        device_id: Intune managed device ID
    """
    return await ios_tools.fix_enrollment_ios(device_id)


@mcp.tool()
async def fix_company_portal_ios(device_id: str) -> dict:
    """
    Force-reinstall Microsoft Company Portal on an iOS device via Intune sync.

    Args:
        device_id: Intune managed device ID
    """
    return await ios_tools.fix_company_portal_ios(device_id)


@mcp.tool()
async def fix_email_profile_ios(device_id: str, user_email: str = None) -> dict:
    """
    Remove and re-push corporate Exchange email profile on iOS.

    Args:
        device_id: Intune managed device ID
        user_email: Optional user email address for context
    """
    return await ios_tools.fix_email_profile_ios(device_id, user_email)


@mcp.tool()
async def fix_app_assignment_ios(device_id: str, app_name: str = None) -> dict:
    """
    Diagnose and sync app assignments for an iOS device.

    Args:
        device_id: Intune managed device ID
        app_name: Optional specific app name to diagnose
    """
    return await ios_tools.fix_app_assignment_ios(device_id, app_name)


@mcp.tool()
async def trigger_os_update_ios(device_id: str, target_version: str = None) -> dict:
    """
    Schedule an iOS/iPadOS OS update via Intune device action.

    Args:
        device_id: Intune managed device ID
        target_version: Optional target iOS version string
    """
    return await ios_tools.trigger_os_update_ios(device_id, target_version)


@mcp.tool()
async def fix_screen_time_policy_ios(device_id: str) -> dict:
    """
    Resolve Screen Time / supervision profile conflicts on an iOS device.

    Args:
        device_id: Intune managed device ID
    """
    return await ios_tools.fix_screen_time_policy_ios(device_id)


@mcp.tool()
async def check_apns_certificate() -> dict:
    """
    Check APNs certificate health in Intune. Warns if expiry is within 60 days.
    Tenant-level check – no device ID required.
    """
    return await ios_tools.check_apns_certificate()


@mcp.tool()
async def get_ios_device_health(device_id: str) -> dict:
    """
    Full health snapshot for an iOS/iPadOS device.
    Returns compliance, OS version, supervision state, profile errors, app failures.

    Args:
        device_id: Intune managed device ID
    """
    return await ios_tools.get_ios_device_health(device_id)


@mcp.tool()
async def clear_passcode_ios(device_id: str, auto_approve: bool = False) -> dict:
    """
    Clear device passcode on a supervised iOS device for locked-out users.
    REQUIRES auto_approve=True – Tier 3 action.

    Args:
        device_id: Intune managed device ID
        auto_approve: Must be True to execute
    """
    return await ios_tools.clear_passcode_ios(device_id, auto_approve)


@mcp.tool()
async def retire_ios_device(device_id: str, auto_approve: bool = False) -> dict:
    """
    Retire an iOS BYOD device: removes corporate apps/profiles, preserves personal data.
    REQUIRES auto_approve=True – Tier 3 action.

    Args:
        device_id: Intune managed device ID
        auto_approve: Must be True to execute
    """
    return await ios_tools.retire_ios_device(device_id, auto_approve)


@mcp.tool()
async def wipe_ios_device(device_id: str, auto_approve: bool = False) -> dict:
    """
    Factory wipe a corporate-owned iOS device. ALL data erased.
    REQUIRES auto_approve=True – Tier 3 critical action.

    Args:
        device_id: Intune managed device ID
        auto_approve: Must be True to execute
    """
    return await ios_tools.wipe_ios_device(device_id, auto_approve)


# ============================================================================
# ANDROID ENTERPRISE REMEDIATION TOOLS  (Issues 85-90 + helpers)
# ============================================================================

@mcp.tool()
async def fix_enrollment_android(device_id: str) -> dict:
    """
    Recover a failed Android Enterprise enrollment. Triggers MDM sync.

    Args:
        device_id: Intune managed device ID
    """
    return await android_tools.fix_enrollment_android(device_id)


@mcp.tool()
async def fix_work_profile_android(device_id: str, user_upn: str = None) -> dict:
    """
    Resolve a missing or broken Android work profile on a BYOD device.

    Args:
        device_id: Intune managed device ID
        user_upn: Optional user UPN
    """
    return await android_tools.fix_work_profile_android(device_id, user_upn)


@mcp.tool()
async def fix_app_assignment_android(device_id: str, app_name: str = None) -> dict:
    """
    Diagnose and sync app assignments for an Android work profile device.

    Args:
        device_id: Intune managed device ID
        app_name: Optional specific app name to diagnose
    """
    return await android_tools.fix_app_assignment_android(device_id, app_name)


@mcp.tool()
async def fix_email_profile_android(device_id: str, user_email: str = None) -> dict:
    """
    Re-push corporate Exchange email profile on Android work profile.

    Args:
        device_id: Intune managed device ID
        user_email: Optional user email
    """
    return await android_tools.fix_email_profile_android(device_id, user_email)


@mcp.tool()
async def trigger_os_update_android(device_id: str, auto_approve: bool = False) -> dict:
    """
    Push OS/security patch update to an Android device via Intune update policy.

    Args:
        device_id: Intune managed device ID
        auto_approve: Set True to proceed without additional confirmation
    """
    return await android_tools.trigger_os_update_android(device_id, auto_approve)


@mcp.tool()
async def fix_company_portal_android(device_id: str) -> dict:
    """
    Fix Microsoft Company Portal app issues on Android (crash, update, cache).

    Args:
        device_id: Intune managed device ID
    """
    return await android_tools.fix_company_portal_android(device_id)


@mcp.tool()
async def get_android_device_health(device_id: str) -> dict:
    """
    Full health snapshot for an Android device.
    Returns compliance, OS version, rooting status, work profile state, app failures.

    Args:
        device_id: Intune managed device ID
    """
    return await android_tools.get_android_device_health(device_id)


@mcp.tool()
async def retire_android_device(device_id: str, auto_approve: bool = False) -> dict:
    """
    Retire an Android BYOD device: removes work profile and corporate data.
    REQUIRES auto_approve=True – Tier 3 action.

    Args:
        device_id: Intune managed device ID
        auto_approve: Must be True to execute
    """
    return await android_tools.retire_android_device(device_id, auto_approve)


@mcp.tool()
async def wipe_android_device(
    device_id: str,
    keep_enrollment_data: bool = False,
    auto_approve: bool = False
) -> dict:
    """
    Factory wipe a corporate-owned Android device. ALL data erased.
    REQUIRES auto_approve=True – Tier 3 critical action.

    Args:
        device_id: Intune managed device ID
        keep_enrollment_data: True for Autopilot-style reset keeping enrollment
        auto_approve: Must be True to execute
    """
    return await android_tools.wipe_android_device(device_id, keep_enrollment_data, auto_approve)


# ============================================================================
# EMPLOYEE LIFECYCLE TOOLS  (Issues 1-15, 16-25, 66-77, 91-100)
# ============================================================================

@mcp.tool()
async def fix_enrollment_autopilot(device_id: str, user_upn: str = None) -> dict:
    """
    Recover a stalled Windows Autopilot enrollment.

    Args:
        device_id: Intune managed device ID
        user_upn: Optional UPN of the user being onboarded
    """
    return await lifecycle_tools.fix_enrollment_autopilot(device_id, user_upn)


@mcp.tool()
async def fix_enrollment_apple_ade(device_serial: str = None) -> dict:
    """
    Recover a failed Apple ADE/DEP enrollment. Syncs all Apple Business Manager tokens.

    Args:
        device_serial: Optional device serial number for tracking
    """
    return await lifecycle_tools.fix_enrollment_apple_ade(device_serial)


@mcp.tool()
async def push_wifi_profile(device_id: str, platform: str = "windows") -> dict:
    """
    Force-sync corporate Wi-Fi configuration profile to a device.

    Args:
        device_id: Intune managed device ID
        platform: windows | macos | ios | android
    """
    return await lifecycle_tools.push_wifi_profile(device_id, platform)


@mcp.tool()
async def push_vpn_profile(device_id: str, platform: str = "windows") -> dict:
    """
    Force-sync corporate VPN configuration profile to a device.

    Args:
        device_id: Intune managed device ID
        platform: windows | macos | ios | android
    """
    return await lifecycle_tools.push_vpn_profile(device_id, platform)


@mcp.tool()
async def push_email_profile(
    device_id: str, platform: str = "ios", user_email: str = None
) -> dict:
    """
    Force-sync corporate Exchange email profile to a mobile device.

    Args:
        device_id: Intune managed device ID
        platform: ios | android
        user_email: Optional user email for context
    """
    return await lifecycle_tools.push_email_profile(device_id, platform, user_email)


@mcp.tool()
async def force_app_installations(device_id: str, app_names: list = None) -> dict:
    """
    Force required app installations on a device by triggering Intune sync.

    Args:
        device_id: Intune managed device ID
        app_names: Optional list of specific app names to check
    """
    return await lifecycle_tools.force_app_installations(device_id, app_names)


@mcp.tool()
async def fix_esp_stuck(device_id: str, auto_approve: bool = False) -> dict:
    """
    Resolve a Windows Autopilot ESP (Enrollment Status Page) that is stuck.

    Args:
        device_id: Intune managed device ID
        auto_approve: Set True to proceed
    """
    return await lifecycle_tools.fix_esp_stuck(device_id, auto_approve)


@mcp.tool()
async def fix_ca_new_device(device_id: str, user_upn: str) -> dict:
    """
    Diagnose why Conditional Access is blocking a newly enrolled device.

    Args:
        device_id: Intune managed device ID
        user_upn: UPN of the blocked user
    """
    return await lifecycle_tools.fix_ca_new_device(device_id, user_upn)


@mcp.tool()
async def enable_device_encryption(device_id: str, platform: str = "windows") -> dict:
    """
    Trigger BitLocker (Windows) or FileVault (macOS) encryption on a device.

    Args:
        device_id: Intune managed device ID
        platform: windows | macos
    """
    return await lifecycle_tools.enable_device_encryption(device_id, platform)


@mcp.tool()
async def fix_azure_ad_registration(device_id: str) -> dict:
    """
    Fix Azure AD device registration issues (missing AAD object, HAADJ broken).

    Args:
        device_id: Intune managed device ID
    """
    return await lifecycle_tools.fix_azure_ad_registration(device_id)


@mcp.tool()
async def set_device_primary_user(device_id: str, user_upn: str) -> dict:
    """
    Set or update the primary user (UDA) for an Intune device.

    Args:
        device_id: Intune managed device ID
        user_upn: UPN of the user to set as primary
    """
    return await lifecycle_tools.set_device_primary_user(device_id, user_upn)


@mcp.tool()
async def assign_device_to_group(device_id: str, group_id: str) -> dict:
    """
    Add a device to an Azure AD group for policy and app targeting.

    Args:
        device_id: Intune managed device ID
        group_id: Azure AD group object ID
    """
    return await lifecycle_tools.assign_device_to_group(device_id, group_id)


@mcp.tool()
async def sync_app_assignments(device_id: str) -> dict:
    """
    Force Intune to re-evaluate and sync all app assignments to a device.

    Args:
        device_id: Intune managed device ID
    """
    return await lifecycle_tools.sync_app_assignments(device_id)


@mcp.tool()
async def fix_mfa_setup(user_upn: str) -> dict:
    """
    Diagnose MFA registration status – identifies missing or stale auth methods.

    Args:
        user_upn: User principal name
    """
    return await lifecycle_tools.fix_mfa_setup(user_upn)


@mcp.tool()
async def unlock_and_reset_password(user_upn: str, auto_approve: bool = False) -> dict:
    """
    Unlock a locked user account and force password reset at next sign-in.

    Args:
        user_upn: User principal name
        auto_approve: Set True to proceed
    """
    return await lifecycle_tools.unlock_and_reset_password(user_upn, auto_approve)


@mcp.tool()
async def fix_authenticator(user_upn: str) -> dict:
    """
    Audit Microsoft Authenticator registrations – identifies stale device entries.

    Args:
        user_upn: User principal name
    """
    return await lifecycle_tools.fix_authenticator(user_upn)


@mcp.tool()
async def renew_scep_certificate(device_id: str) -> dict:
    """
    Trigger SCEP/PKCS certificate renewal via Intune sync.
    Fixes Wi-Fi, VPN, and app auth certificate failures.

    Args:
        device_id: Intune managed device ID
    """
    return await lifecycle_tools.renew_scep_certificate(device_id)


@mcp.tool()
async def diagnose_compliance(device_id: str) -> dict:
    """
    Detailed compliance diagnosis for any device type.
    Reads all compliance policy states and identifies specific failures.

    Args:
        device_id: Intune managed device ID
    """
    return await lifecycle_tools.diagnose_compliance(device_id)


@mcp.tool()
async def trigger_os_update(device_id: str, platform: str = "windows") -> dict:
    """
    Trigger an OS update on a non-compliant device via Intune update policy.

    Args:
        device_id: Intune managed device ID
        platform: windows | macos | ios | android
    """
    return await lifecycle_tools.trigger_os_update(device_id, platform)


@mcp.tool()
async def block_unsanctioned_app(
    device_id: str, app_package_name: str, auto_approve: bool = False
) -> dict:
    """
    Flag and block an unsanctioned app via compliance policy re-evaluation.

    Args:
        device_id: Intune managed device ID
        app_package_name: Package name or display name of the app to block
        auto_approve: Set True to proceed
    """
    return await lifecycle_tools.block_unsanctioned_app(device_id, app_package_name, auto_approve)


@mcp.tool()
async def quarantine_device(device_id: str, auto_approve: bool = False) -> dict:
    """
    Quarantine a jailbroken/rooted device: remote lock + CA access revoked.
    REQUIRES auto_approve=True – Tier 3.

    Args:
        device_id: Intune managed device ID
        auto_approve: Must be True to quarantine
    """
    return await lifecycle_tools.quarantine_device(device_id, auto_approve)


@mcp.tool()
async def verify_bitlocker_escrow(device_id: str) -> dict:
    """
    Verify BitLocker recovery key is escrowed in Azure AD / Intune.
    Run this before any device wipe to confirm key is safe.

    Args:
        device_id: Intune managed device ID
    """
    return await lifecycle_tools.verify_bitlocker_escrow(device_id)


@mcp.tool()
async def wipe_offboarded_device(
    device_id: str,
    device_type: str = "corporate",
    auto_approve: bool = False
) -> dict:
    """
    Wipe or retire a departed employee's device.
    Corporate = factory wipe. BYOD = retire (preserves personal data).
    REQUIRES auto_approve=True – Tier 3.

    Args:
        device_id: Intune managed device ID
        device_type: corporate | byod
        auto_approve: Must be True to execute
    """
    return await lifecycle_tools.wipe_offboarded_device(device_id, device_type, auto_approve)


@mcp.tool()
async def autopilot_reset(device_id: str, auto_approve: bool = False) -> dict:
    """
    Trigger Autopilot Reset to reprovision a Windows device for the next employee.
    Keeps enrollment data; removes user data.
    REQUIRES auto_approve=True – Tier 3.

    Args:
        device_id: Intune managed device ID
        auto_approve: Must be True to execute
    """
    return await lifecycle_tools.autopilot_reset(device_id, auto_approve)


@mcp.tool()
async def cleanup_aad_device(
    device_id: str, aad_device_id: str, auto_approve: bool = False
) -> dict:
    """
    Delete a stale Azure AD device object after offboarding.

    Args:
        device_id: Intune managed device ID
        aad_device_id: Azure AD device object ID
        auto_approve: Set True to proceed with deletion
    """
    return await lifecycle_tools.cleanup_aad_device(device_id, aad_device_id, auto_approve)


@mcp.tool()
async def reclaim_user_licenses(user_upn: str, auto_approve: bool = False) -> dict:
    """
    Remove all M365 license assignments from a departed user.

    Args:
        user_upn: Departed user's UPN
        auto_approve: Set True to proceed
    """
    return await lifecycle_tools.reclaim_user_licenses(user_upn, auto_approve)


@mcp.tool()
async def revoke_user_access(user_upn: str, auto_approve: bool = False) -> dict:
    """
    Revoke all sessions/tokens and disable account for a departed employee.

    Args:
        user_upn: Departed user's UPN
        auto_approve: Set True to proceed
    """
    return await lifecycle_tools.revoke_user_access(user_upn, auto_approve)


@mcp.tool()
async def remove_from_intune(device_id: str, auto_approve: bool = False) -> dict:
    """
    Delete a stale Intune device record after factory reset.

    Args:
        device_id: Intune managed device ID
        auto_approve: Set True to proceed
    """
    return await lifecycle_tools.remove_from_intune(device_id, auto_approve)


@mcp.tool()
async def transfer_onedrive_data(
    from_user_upn: str, to_user_upn: str, auto_approve: bool = False
) -> dict:
    """
    Grant manager access to a departed employee's OneDrive files.

    Args:
        from_user_upn: Departing employee's UPN
        to_user_upn: Manager's UPN to receive access
        auto_approve: Set True to proceed
    """
    return await lifecycle_tools.transfer_onedrive_data(from_user_upn, to_user_upn, auto_approve)


@mcp.tool()
async def reprovision_shared_device(device_id: str, new_user_upn: str = None) -> dict:
    """
    Re-provision a shared/kiosk device for the next employee.
    Updates primary user and triggers policy re-evaluation.

    Args:
        device_id: Intune managed device ID
        new_user_upn: UPN of the next user assigned to the device
    """
    return await lifecycle_tools.reprovision_shared_device(device_id, new_user_upn)


# ============================================================================
# LIFECYCLE ORCHESTRATION  (full checklist workflows)
# ============================================================================

@mcp.tool()
async def run_onboarding_checklist(
    device_id: str, user_upn: str, platform: str = "windows"
) -> dict:
    """
    Run the complete device onboarding health checklist for a new employee.
    Checks: enrollment, AAD registration, compliance, encryption, primary user,
    required apps, and configuration profiles. Returns a scored checklist.

    Args:
        device_id: Intune managed device ID
        user_upn: New employee's UPN
        platform: windows | macos | ios | android
    """
    return await lifecycle_tools.run_onboarding_checklist(device_id, user_upn, platform)


@mcp.tool()
async def run_offboarding_checklist(device_id: str, user_upn: str) -> dict:
    """
    Run the complete offboarding checklist for a departing employee.
    Checks: wipe status, BitLocker escrow, account disabled, licenses reclaimed,
    OneDrive transferred. Returns TODO list with actions required.

    Args:
        device_id: Intune managed device ID
        user_upn: Departing employee's UPN
    """
    return await lifecycle_tools.run_offboarding_checklist(device_id, user_upn)


# ============================================================================
# RUN SERVER (Moved to end to ensure all tools are registered)
# ============================================================================

if __name__ == "__main__":
    import sys
    import uvicorn

    # Cloud providers (Render, AWS) provide a PORT env var
    port = int(os.environ.get("PORT", 8000))
    
    # Check if we should force stdio mode (for CLI/MCP subprocess)
    # Otherwise default to HTTP for Cloud/Docker dashboard support
    transport = os.environ.get("MCP_TRANSPORT", "http").lower()
    
    if transport == "stdio" or (not sys.stdin.isatty() and transport != "http"):
        # ── Stdio mode (MCP subprocess) ───────────────────────────────────────
        logger.info("Starting MCP server in Stdio mode")
        mcp.run()
    else:
        # ── HTTP mode (Cloud / Docker / Dashboad) ─────────────────────────────
        logger.info("Starting Intune Device Healer Unified Server", port=port)
        logger.info(
            "Endpoints ready",
            mcp="/mcp",
            dashboard="/",
            webhook="/webhook/ticket",
            health="/healthz"
        )
        uvicorn.run(
            "server:app",
            host="0.0.0.0",
            port=port,
            log_config=None,   # use structlog
            timeout_graceful_shutdown=30,
        )
