"""
Atomicwork Webhook Integration for Intune Device Healer
FastAPI app that receives Atomicwork ticket webhooks, queries the Atomicwork API
to fetch full ticket + asset details (including Intune Device ID), then runs
automated remediation via Microsoft Intune/Graph API.

Flow:
  Atomicwork webhook → POST /webhook/ticket  { "display_id": "DWINC-7947" }
      → Lambda queries Atomicwork API → GET /api/v1/requests/DWINC-7947
      → Extract Intune Device ID from assets[0].form_fields
      → Detect issue type from subject/description
      → Run automated remediation on device
"""

import os
import sys
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx
import structlog

# Configure logging to stderr
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)
)

logger = structlog.get_logger()

# ============================================================================
# ATOMICWORK API CLIENT
# Queries Atomicwork to fetch full ticket + asset details from just a ticket ID
# ============================================================================

# Atomicwork custom field key that holds the Intune Device ID (discovered from API response)
INTUNE_DEVICE_ID_FIELD = "af_6d16f9f4_d8be_0b02_98e5_d21259234dc5_1771231002279"

# OS type IDs from Atomicwork (from real API response)
# operating_system: 26528 = Windows, 26526 = macOS, 171800 = Android
OS_PLATFORM_MAP = {
    26528: "Windows",
    26526: "macOS",
    171800: "Android",
    171801: "Android",  # android variant
}


class AtomicworkClient:
    """Client for Atomicwork REST API"""

    def __init__(self):
        self.base_url = os.environ.get(
            "ATOMICWORK_BASE_URL", "https://atombanking.atomicwork.com"
        )
        self.api_key = os.environ.get("ATOMICWORK_API_KEY", "")
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def post_note(self, display_id: str, html: str, is_private: bool = False) -> Dict[str, Any]:
        """
        Post an activity note on a ticket.
        API: POST /api/v1/requests/{display_id}/activity-notes
        Body: { "description": "<html>...", "is_private": "false", "source": "PORTAL" }
        """
        url = f"{self.base_url}/api/v1/requests/{display_id}/activity-notes"
        payload = {
            "description": html,
            "is_private": "true" if is_private else "false",
            "source": "PORTAL"
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self.headers, json=payload)

        if response.status_code not in (200, 201):
            logger.error(
                f"Failed to post note on {display_id}: "
                f"HTTP {response.status_code} {response.text[:200]}"
            )
            return {"success": False, "error": response.text[:200]}

        return {"success": True, "data": response.json()}

    async def get_ticket(self, display_id: str) -> Dict[str, Any]:
        """
        Fetch full ticket details from Atomicwork API.
        Returns the raw API response as a dict.
        Raises HTTPException if not found or API error.
        """
        url = f"{self.base_url}/api/v1/requests/{display_id}"
        logger.info(f"Fetching ticket from Atomicwork: {url}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)

        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Ticket {display_id} not found in Atomicwork"
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Atomicwork API error {response.status_code}: {response.text[:200]}"
            )

        return response.json()

    def extract_device_info(self, ticket_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract device/asset information from a ticket API response.
        Iterates through all linked assets to find one with an Intune ID.
        """
        assets = ticket_data.get("assets", [])
        if not assets:
            logger.warning("No assets found in ticket data")
            return None

        # Look for the asset with an Intune Device ID
        target_asset = None
        intune_device_id = None
        
        for asset in assets:
            form_fields = asset.get("form_fields", {})
            intune_id = form_fields.get(INTUNE_DEVICE_ID_FIELD)
            if intune_id:
                target_asset = asset
                intune_device_id = intune_id
                break
        
        # Fallback to the first asset if none have an Intune ID
        if not target_asset and assets:
            target_asset = assets[0]
            logger.info(f"No asset found with Intune ID field; using first asset: {target_asset.get('label')}")

        if not target_asset:
            return None

        form_fields = target_asset.get("form_fields", {})
        
        # Determine platform from operating_system field
        os_type_id = form_fields.get("operating_system")
        platform = OS_PLATFORM_MAP.get(os_type_id, "Windows")

        # Fallback inference if OS type ID is missing
        if os_type_id not in OS_PLATFORM_MAP:
            label = target_asset.get("label", "").lower()
            if any(kw in label for kw in ["mac", "apple", "studio", "pro", "air"]):
                platform = "macOS"
            elif any(kw in label for kw in ["android", "iphone", "ipad", "pixel", "samsung"]):
                platform = "Android"
            else:
                platform = "Windows"

        return {
            "asset_id": str(target_asset.get("id", "")),
            "asset_name": target_asset.get("label", form_fields.get("display_name", "Unknown")),
            "intune_device_id": intune_device_id,
            "serial_number": target_asset.get("serial_number"),
            "platform": platform,
            "source": target_asset.get("source", {}).get("display_name", "Unknown"),
            "last_connected": form_fields.get("last_connected"),
        }

    def extract_ticket_info(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract normalized ticket fields from raw Atomicwork API response"""
        return {
            "ticket_id": ticket_data.get("display_id", str(ticket_data.get("id", ""))),
            "subject": ticket_data.get("subject", ""),
            "description": ticket_data.get("description_text", "") or
                          ticket_data.get("description", ""),
            "priority": ticket_data.get("priority", {}).get("label", "Medium").lower(),
            "status": ticket_data.get("status", {}).get("label", "Open"),
            "requester_email": ticket_data.get("requester", {}).get("email", ""),
            "requester_name": ticket_data.get("requester", {}).get("label", ""),
            "assignee_email": (ticket_data.get("assignee") or {}).get("email"),
            "created_at": ticket_data.get("created_at"),
            "workspace_id": ticket_data.get("workspace_id"),
        }


# ============================================================================
# LAZY INITIALIZATION
# Only instantiate tools on first request to avoid Lambda cold-start failures
# ============================================================================

_config = None
_authenticator = None
_diagnostic_tools = None
_windows_tools = None
_macos_tools = None
_automation_tools = None
_monitoring_tools = None
_atomicwork_client = None


def get_config():
    global _config
    if _config is None:
        from core.config import Config
        _config = Config()
    return _config


def get_authenticator():
    global _authenticator
    if _authenticator is None:
        from core.auth import GraphAuthenticator
        _authenticator = GraphAuthenticator(get_config())
    return _authenticator


def get_diagnostic_tools():
    global _diagnostic_tools
    if _diagnostic_tools is None:
        from tools.diagnostic import DiagnosticTools
        _diagnostic_tools = DiagnosticTools(get_authenticator(), get_config())
    return _diagnostic_tools


def get_windows_tools():
    global _windows_tools
    if _windows_tools is None:
        from tools.windows_remediation import WindowsRemediationTools
        _windows_tools = WindowsRemediationTools(get_authenticator(), get_config())
    return _windows_tools


def get_macos_tools():
    global _macos_tools
    if _macos_tools is None:
        from tools.macos_remediation import MacOSRemediationTools
        _macos_tools = MacOSRemediationTools(get_authenticator(), get_config())
    return _macos_tools


def get_automation_tools():
    global _automation_tools
    if _automation_tools is None:
        from tools.automation import AutomationTools
        _automation_tools = AutomationTools(get_authenticator(), get_config())
    return _automation_tools


def get_monitoring_tools():
    global _monitoring_tools
    if _monitoring_tools is None:
        from tools.monitoring import MonitoringTools
        _monitoring_tools = MonitoringTools(get_authenticator(), get_config())
    return _monitoring_tools


def get_worklets_tools():
    global _worklets_tools
    if "_worklets_tools" not in globals() or _worklets_tools is None:
        from tools.worklets import WorkletsTools
        _worklets_tools = WorkletsTools(get_authenticator(), get_config())
    return _worklets_tools


def get_atomicwork_client():
    global _atomicwork_client
    if _atomicwork_client is None:
        _atomicwork_client = AtomicworkClient()
    return _atomicwork_client


# ============================================================================
# FASTAPI APP
# ============================================================================

# ============================================================================
# MCP HTTP ENDPOINT
# Mounts all 67 MCP tools at /mcp using FastMCP's streamable-http transport.
# stateless_http=True is required for Lambda (no persistent connections).
# Protected by X-MCP-API-Key header — MCP_API_KEY stored in SSM/Lambda env.
#
# Claude Desktop / Claude.ai config to connect (share this with your team):
#   {
#     "mcpServers": {
#       "intune-device-healer": {
#         "type": "http",
#         "url": "https://ls3gx9r06h.execute-api.us-east-1.amazonaws.com/prod/mcp",
#         "headers": { "X-MCP-API-Key": "<your-key>" }
#       }
#     }
#   }
# ============================================================================

# Build the MCP Starlette app first so we can wire its lifespan into FastAPI.
# FastMCP's streamable-http transport requires the lifespan to be passed to the
# parent ASGI app — without it the session manager task group is never started.
_mcp_starlette = None
_mcp_lifespan   = None

app = FastAPI(
    title="Intune Device Healer - Atomicwork Integration",
    description="AI-powered automatic device remediation from Atomicwork tickets",
    version="2.0.0",
)


# ============================================================================
# REQUEST MODELS
# Atomicwork only needs to send the ticket display_id in the webhook.
# Everything else is fetched from the Atomicwork API.
# ============================================================================

class AtomicworkWebhookPayload(BaseModel):
    """
    Minimal payload that Atomicwork sends via webhook.
    Only the ticket display_id is required - all other data is fetched from the API.
    """
    display_id: str                          # e.g. "DWINC-7947"
    event_type: Optional[str] = "ticket_created"   # optional context


class ManualRemediationRequest(BaseModel):
    """For manually triggering remediation on a known device"""
    device_id: str
    actions: List[str]
    platform: str = "Windows"


class AnalyzeRequest(BaseModel):
    """For testing ticket analysis without remediation"""
    subject: str
    description: str
    platform: Optional[str] = "Windows"


class AutoHealRequest(BaseModel):
    """Unified request for context-driven remediation"""
    subject: str
    description: str
    device_id: str
    platform: Optional[str] = "Windows"


# ============================================================================
# REMEDIATION NOTE FORMATTER
# Builds the HTML note posted back to the Atomicwork ticket.
# Rules: no emoji, no em-dash, no filler phrases, no AI-style language.
# Plain factual report of what ran, what succeeded, what failed.
# ============================================================================

class RemediationNoteBuilder:
    """
    Builds two notes for every remediation:
      1. build()            -> private HTML technical report (for IT agents)
      2. build_user_reply() -> public plain-English reply (for the end user)
    """

    # ------------------------------------------------------------------
    # PRIVATE TECHNICAL NOTE
    # Full detail: device info, Intune ID, script breakdown, disk stats.
    # Posted as is_private=True so only agents see it.
    # ------------------------------------------------------------------
    @staticmethod
    def build(
        display_id: str,
        ticket_info: Dict[str, Any],
        device_info: Dict[str, Any],
        analysis: Dict[str, Any],
        remediation_result: Dict[str, Any],
    ) -> str:
        device_name   = device_info.get("asset_name", "Unknown")
        platform      = device_info.get("platform", "Unknown")
        intune_id     = device_info.get("intune_device_id", "Unknown")
        serial        = device_info.get("serial_number", "N/A")
        last_seen     = device_info.get("last_connected", "N/A")
        issue_type    = analysis.get("issue_type", "unknown").replace("_", " ").title()
        executed      = remediation_result.get("executed", [])
        failed        = remediation_result.get("failed", [])
        overall_ok    = remediation_result.get("overall_success", False)
        ts            = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        # ---- disk stats row (if present in any executed action) ----
        disk_stats_rows = ""
        for item in executed:
            ds = item.get("result", {}).get("disk_stats", {})
            if ds:
                before  = ds.get("free_before_gb", "")
                after   = ds.get("free_after_gb", "")
                recl_gb = ds.get("reclaimed_gb", "")
                recl_mb = ds.get("reclaimed_mb", "")
                total   = ds.get("total_gb", "")
                disk_stats_rows = f"""
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Drive Total</td><td style="padding:3px 0;">{total} GB</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Free Before</td><td style="padding:3px 0;">{before} GB</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Free After</td><td style="padding:3px 0;font-weight:600;">{after} GB</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Reclaimed</td><td style="padding:3px 0;font-weight:600;color:#15803d;">{recl_gb} GB ({recl_mb} MB)</td></tr>"""
                break

        # ---- action rows ----
        action_rows = ""
        for item in executed:
            action_label = item["action"].replace("_", " ").title()
            ok           = item.get("success", False)
            status_cell  = (
                '<td style="color:#1a7a3c;font-weight:600;padding:5px 10px;border:1px solid #e5e7eb;">Deployed</td>'
                if ok else
                '<td style="color:#b91c1c;font-weight:600;padding:5px 10px;border:1px solid #e5e7eb;">Failed</td>'
            )
            result_data  = item.get("result", {})
            detail       = (
                result_data.get("message")
                or result_data.get("status")
                or result_data.get("details")
                or ""
            )
            if isinstance(detail, dict):
                detail = str(detail)
            detail = str(detail)[:160]

            action_rows += (
                f"<tr>"
                f"<td style='padding:5px 10px;border:1px solid #e5e7eb;'>{action_label}</td>"
                f"{status_cell}"
                f"<td style='padding:5px 10px;border:1px solid #e5e7eb;color:#555;font-size:12px;'>{detail}</td>"
                f"</tr>"
            )

        for item in failed:
            action_label = item["action"].replace("_", " ").title()
            err          = str(item.get("error", ""))[:160]
            action_rows += (
                f"<tr>"
                f"<td style='padding:5px 10px;border:1px solid #e5e7eb;'>{action_label}</td>"
                f"<td style='color:#b91c1c;font-weight:600;padding:5px 10px;border:1px solid #e5e7eb;'>Failed</td>"
                f"<td style='padding:5px 10px;border:1px solid #e5e7eb;color:#555;font-size:12px;'>{err}</td>"
                f"</tr>"
            )

        if not action_rows:
            action_rows = "<tr><td colspan='3' style='padding:5px 10px;border:1px solid #e5e7eb;'>No actions were executed.</td></tr>"

        # ---- overall status banner ----
        if overall_ok:
            status_banner = (
                '<p style="background:#f0fdf4;border-left:3px solid #16a34a;'
                'padding:8px 12px;margin:12px 0;color:#15803d;font-size:13px;">'
                'All remediation scripts deployed without errors. Scripts will execute on the device at next Intune check-in.'
                '</p>'
            )
        else:
            status_banner = (
                '<p style="background:#fef2f2;border-left:3px solid #dc2626;'
                'padding:8px 12px;margin:12px 0;color:#b91c1c;font-size:13px;">'
                f'{len(failed)} action(s) failed to deploy. Review the action table below.'
                '</p>'
            )

        html = f"""<div style="font-family:Arial,sans-serif;font-size:13px;color:#1a1a1a;max-width:720px;">

<p style="margin:0 0 12px 0;font-size:14px;font-weight:600;border-bottom:2px solid #e5e7eb;padding-bottom:8px;">
  Automated Remediation Report <span style="font-weight:400;color:#9ca3af;font-size:11px;">[Private (Internal IT Agent)]</span>
</p>

<table style="border-collapse:collapse;width:100%;margin-bottom:14px;">
  <tr><td style="padding:3px 12px 3px 0;color:#555;width:140px;">Ticket</td><td style="padding:3px 0;font-weight:600;">{display_id}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Device</td><td style="padding:3px 0;">{device_name}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Platform</td><td style="padding:3px 0;">{platform}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Serial</td><td style="padding:3px 0;">{serial}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Intune ID</td><td style="padding:3px 0;font-size:11px;color:#555;">{intune_id}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Last Seen</td><td style="padding:3px 0;">{last_seen}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Issue Detected</td><td style="padding:3px 0;">{issue_type}</td></tr>
  <tr><td style="padding:3px 12px 3px 0;color:#555;">Triggered At</td><td style="padding:3px 0;">{ts}</td></tr>
  {disk_stats_rows}
</table>

{status_banner}

<p style="font-weight:600;margin:14px 0 6px 0;">Remediation Actions</p>
<table style="border-collapse:collapse;width:100%;font-size:12px;">
  <thead>
    <tr style="background:#f3f4f6;">
      <th style="text-align:left;padding:6px 10px;border:1px solid #e5e7eb;width:35%;">Action</th>
      <th style="text-align:left;padding:6px 10px;border:1px solid #e5e7eb;width:12%;">Status</th>
      <th style="text-align:left;padding:6px 10px;border:1px solid #e5e7eb;">Detail</th>
    </tr>
  </thead>
  <tbody>{action_rows}</tbody>
</table>

<p style="margin:14px 0 0 0;font-size:11px;color:#9ca3af;">
  Intune Device Healer (Automated Response) | {ts}
</p>
</div>"""

        return html

    # ------------------------------------------------------------------
    # PUBLIC USER-FACING REPLY
    # Short, plain English. No jargon. Tells the user what was done.
    # Posted as is_private=False so the user sees it in their ticket.
    # ------------------------------------------------------------------
    @staticmethod
    def build_user_reply(
        device_info: Dict[str, Any],
        analysis: Dict[str, Any],
        remediation_result: Dict[str, Any],
    ) -> str:
        device_name = device_info.get("asset_name", "your device")
        platform    = device_info.get("platform", "")
        issue_type  = analysis.get("issue_type", "unknown")
        executed    = remediation_result.get("executed", [])
        failed      = remediation_result.get("failed", [])
        overall_ok  = remediation_result.get("overall_success", False)

        # Build a human-readable action summary
        action_lines = []
        for item in executed:
            action = item["action"]
            result_data = item.get("result", {})
            ds = result_data.get("disk_stats", {})

            if action == "cleanup_disk_space" and ds:
                recl_gb = ds.get("reclaimed_gb", "")
                recl_mb = ds.get("reclaimed_mb", "")
                before  = ds.get("free_before_gb", "")
                after   = ds.get("free_after_gb", "")
                action_lines.append(
                    f"<li><b>Disk cleanup</b> ran on {device_name}. "
                    f"{recl_gb} GB ({recl_mb} MB) of temporary files were removed. "
                    f"Free space increased from {before} GB to {after} GB.</li>"
                )
            elif action == "cleanup_disk_space":
                action_lines.append(
                    f"<li><b>Disk cleanup</b> script was sent to {device_name} via Intune. "
                    f"Temporary files will be cleared at the next device check-in.</li>"
                )
            elif action == "reset_network_stack":
                action_lines.append(
                    f"<li><b>Network stack reset</b> was applied to {device_name}. "
                    f"DNS cache flushed, TCP/IP and Winsock reset. A restart may be required.</li>"
                )
            elif action in ("fix_vpn_configuration", "fix_vpn_profile_mac"):
                action_lines.append(
                    f"<li><b>VPN configuration</b> was repaired on {device_name}.</li>"
                )
            elif action == "repair_outlook_pst":
                action_lines.append(
                    f"<li><b>Outlook data file (PST)</b> repair was initiated on {device_name}. "
                    f"Outlook should be restarted after the script completes.</li>"
                )
            elif action == "fix_outlook_mac":
                action_lines.append(
                    f"<li><b>Outlook for Mac</b> profile and cache repair was initiated on {device_name}.</li>"
                )
            elif action == "fix_windows_updates":
                action_lines.append(
                    f"<li><b>Windows Update</b> components were reset on {device_name}. "
                    f"Updates should resume automatically.</li>"
                )
            elif action == "repair_system_files":
                action_lines.append(
                    f"<li><b>System file repair</b> (SFC/DISM) was triggered on {device_name}.</li>"
                )
            elif action == "reset_network_settings_mac":
                action_lines.append(
                    f"<li><b>Network settings</b> were reset on {device_name} (macOS).</li>"
                )
            elif action == "reset_smc":
                action_lines.append(
                    f"<li><b>SMC reset</b> was performed on {device_name}. "
                    f"This addresses power, thermal, and battery issues.</li>"
                )
            elif action in ("check_hardware_health", "check_network_health",
                            "check_application_health", "check_os_health",
                            "diagnose_comprehensive"):
                action_lines.append(
                    f"<li><b>Diagnostic check</b> was run on {device_name}.</li>"
                )
            else:
                label = action.replace("_", " ").title()
                action_lines.append(f"<li><b>{label}</b> was applied to {device_name}.</li>")

        if not action_lines:
            action_lines = [f"<li>No automated actions were applied to {device_name}.</li>"]

        actions_html = "\n".join(action_lines)

        if overall_ok and not failed:
            status_line = (
                f'<p style="background:#f0fdf4;border-left:3px solid #16a34a;'
                f'padding:8px 12px;margin:0 0 14px 0;color:#15803d;font-size:13px;">'
                f'The issue on {device_name} has been resolved automatically.</p>'
            )
            closing = (
                "<p>No further action is needed. If the problem persists after the next device "
                "restart, reply to this ticket and the IT team will follow up.</p>"
            )
        else:
            status_line = (
                f'<p style="background:#fef2f2;border-left:3px solid #dc2626;'
                f'padding:8px 12px;margin:0 0 14px 0;color:#b91c1c;font-size:13px;">'
                f'Some tasks require manual intervention on {device_name}. '
                f'An IT agent has been updated.</p>'
            )
            closing = (
                "<p>An IT agent will review the remaining items and follow up as needed.</p>"
            )

        html = f"""<div style="font-family:Arial,sans-serif;font-size:13px;color:#1a1a1a;max-width:680px;">

{status_line}

<p style="margin:0 0 8px 0;font-weight:600;">What was done:</p>
<ul style="margin:0 0 14px 0;padding-left:18px;line-height:1.7;">
{actions_html}
</ul>

{closing}

</div>"""

        return html


# ============================================================================
# AI TICKET ANALYZER
# ============================================================================

class TicketAnalyzer:
    """Analyzes ticket content and maps to appropriate remediation actions"""

    PATTERNS = {
        "vpn": {
            "keywords": ["vpn", "virtual private network", "vpn not working", "cannot connect vpn",
                         "tunneling", "remote access", "cisco anyconnect", "globalprotect"],
            "windows_actions": ["fix_vpn_configuration"],
            "macos_actions": ["fix_vpn_profile_mac"],
            "diagnostic_actions": ["check_network_health"],
            "priority": "high"
        },
        "outlook": {
            "keywords": ["outlook", "email", "pst", "ost", "cannot send email", "outlook crash",
                         "mail not working", "emails not loading", "exchange", "inbox"],
            "windows_actions": ["repair_outlook_pst"],
            "macos_actions": ["fix_outlook_mac"],
            "diagnostic_actions": ["check_application_health"],
            "priority": "high"
        },
        "printer": {
            "keywords": ["printer", "printing", "print", "spooler", "cannot print", "stuck print", "printer queue"],
            "windows_actions": ["fix_printer_spooler"],
            "macos_actions": [],
            "diagnostic_actions": ["check_hardware_health"],
            "priority": "medium"
        },
        "network": {
            "keywords": ["network", "internet", "wifi", "no connection", "cannot connect", "offline",
                         "no internet", "wifi issue", "ethernet", "ping failing", "dns"],
            "windows_actions": ["reset_network_stack"],
            "macos_actions": ["reset_network_settings_mac"],
            "diagnostic_actions": ["check_network_health"],
            "priority": "high"
        },
        "disk": {
            "keywords": ["disk full", "low disk space", "storage full", "out of space", "disk cleanup",
                         "no space", "drive full", "c drive", "storage issue"],
            "windows_actions": ["cleanup_disk_space"],
            "macos_actions": ["cleanup_disk_space"],
            "diagnostic_actions": ["check_hardware_health"],
            "priority": "medium"
        },
        "performance": {
            "keywords": ["slow", "performance", "hanging", "freezing", "lag", "sluggish",
                         "unresponsive", "taking too long", "computer slow", "laptop slow",
                         "cpu high", "memory high", "ram usage", "fan loud"],
            "windows_actions": ["get_performance_diagnostics_windows", "get_detailed_disk_usage_windows", "cleanup_disk_space"],
            "macos_actions": ["get_performance_diagnostics_mac", "get_detailed_disk_usage_mac", "reset_smc"],
            "diagnostic_actions": ["check_hardware_health"],
            "priority": "medium"
        },
        "updates": {
            "keywords": ["windows update", "update failed", "update error", "not updating",
                         "cumulative update", "feature update", "patch"],
            "windows_actions": ["fix_windows_updates"],
            "macos_actions": [],
            "diagnostic_actions": ["check_os_health"],
            "priority": "medium"
        },
        "system": {
            "keywords": ["blue screen", "bsod", "crash", "system error", "corrupted",
                         "kernel panic", "system crash", "not booting", "startup issue"],
            "windows_actions": ["repair_system_files"],
            "macos_actions": ["reset_nvram", "reset_smc"],
            "diagnostic_actions": ["check_os_health"],
            "priority": "critical"
        }
    }

    @classmethod
    def analyze(cls, subject: str, description: str, platform: str = "Windows") -> Dict[str, Any]:
        text = f"{subject} {description}".lower()
        matches = []

        for issue_type, pattern in cls.PATTERNS.items():
            hits = sum(1 for kw in pattern["keywords"] if kw in text)
            if hits > 0:
                matches.append({
                    "issue_type": issue_type,
                    "hits": hits,
                    "confidence": round(min(hits / max(len(pattern["keywords"]), 1), 1.0), 2),
                    "windows_actions": pattern["windows_actions"],
                    "macos_actions": pattern["macos_actions"],
                    "diagnostic_actions": pattern["diagnostic_actions"],
                    "priority": pattern["priority"]
                })

        if not matches:
            return {
                "issue_type": "unknown",
                "confidence": 0.5,
                "actions": ["diagnose_comprehensive"],
                "priority": "medium",
                "reasoning": "No specific issue detected - running comprehensive diagnostic"
            }

        matches.sort(key=lambda x: (x["hits"], x["confidence"]), reverse=True)
        best = matches[0]

        is_macos = platform.lower() in ("macos", "mac", "darwin")
        remedy = best["macos_actions"] if is_macos else best["windows_actions"]

        return {
            "issue_type": best["issue_type"],
            "confidence": best["confidence"],
            "actions": best["diagnostic_actions"] + remedy,
            "priority": best["priority"],
            "reasoning": f"Detected '{best['issue_type']}' issue based on ticket content"
        }


# ============================================================================
# REMEDIATION EXECUTOR
# ============================================================================

async def run_remediation(device_id: str, actions: List[str], platform: str) -> Dict[str, Any]:
    """Execute a list of remediation actions on a device"""

    diag = get_diagnostic_tools()
    win = get_windows_tools()
    mac = get_macos_tools()
    auto = get_automation_tools()
    worklets = get_worklets_tools()

    action_map = {
        # Diagnostics
        "diagnose_comprehensive":      diag.diagnose_comprehensive,
        "check_hardware_health":       diag.check_hardware,
        "check_os_health":             diag.check_os,
        "check_network_health":        diag.check_network,
        "check_security_posture":      diag.check_security,
        "check_application_health":    diag.check_applications,
        "predict_failures":            diag.predict_failures,
        # Windows
        "fix_windows_updates":         win.fix_windows_updates,
        "repair_system_files":         win.repair_system_files,
        "cleanup_disk_space":          win.cleanup_disk_space,
        "reset_network_stack":         win.reset_network_stack,
        "fix_vpn_configuration":       win.fix_vpn_configuration,
        "repair_outlook_pst":          win.repair_outlook_pst,
        "rebuild_outlook_profile":     win.rebuild_outlook_profile,
        "repair_disk_errors":          win.repair_disk_errors,
        "enable_bitlocker":            win.enable_bitlocker,
        "update_drivers_auto":         win.update_drivers_auto,
        # macOS
        "reset_smc":                   mac.reset_smc,
        "reset_nvram":                 mac.reset_nvram,
        "repair_disk_permissions_mac": mac.repair_disk_permissions,
        "fix_spotlight_index":         mac.fix_spotlight_index,
        "reset_network_settings_mac":  mac.reset_network_settings,
        "fix_vpn_profile_mac":         mac.fix_vpn_profile,
        "fix_outlook_mac":             mac.fix_outlook_mac,
        # Performance & Deep Diagnostics
        "get_performance_diagnostics_windows": worklets.get_performance_diagnostics_windows,
        "get_performance_diagnostics_mac":     worklets.get_performance_diagnostics_mac,
        "get_detailed_disk_usage_windows":     worklets.get_detailed_disk_usage_windows,
        "get_detailed_disk_usage_mac":         worklets.get_detailed_disk_usage_mac,
        "fix_printer_spooler":                 worklets.fix_printer_spooler,
        # Automation
        "auto_heal_device":            auto.auto_heal_device,
    }

    executed = []
    failed = []

    for action_name in actions:
        fn = action_map.get(action_name)
        if not fn:
            failed.append({"action": action_name, "error": "Unknown action"})
            continue
        try:
            logger.info(f"Executing {action_name} on device {device_id}")
            result = await fn(device_id)
            executed.append({
                "action": action_name,
                "success": result.get("success", True),
                "result": result
            })
        except Exception as e:
            logger.error(f"Failed {action_name}: {str(e)}")
            failed.append({"action": action_name, "error": str(e)})

    return {
        "device_id": device_id,
        "platform": platform,
        "executed": executed,
        "failed": failed,
        "overall_success": len(failed) == 0,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# BACKGROUND TICKET PROCESSOR
# Runs after webhook returns 202 - does the actual work
# ============================================================================

async def process_ticket_background(display_id: str, event_type: str):
    """
    Full ticket processing pipeline:
    1. Query Atomicwork API to get ticket + asset details
    2. Extract Intune Device ID and platform
    3. Analyze ticket to determine remediation actions
    4. Execute remediation
    """
    try:
        client = get_atomicwork_client()

        # Step 1: Fetch full ticket from Atomicwork
        logger.info(f"Fetching ticket {display_id} from Atomicwork API")
        ticket_data = await client.get_ticket(display_id)

        # Step 2: Extract ticket info
        ticket_info = client.extract_ticket_info(ticket_data)
        device_info = client.extract_device_info(ticket_data)

        logger.info(f"Ticket: {ticket_info['subject']} | Requester: {ticket_info['requester_email']}")

        if not device_info:
            logger.warning(f"Ticket {display_id} has no linked asset - skipping remediation")
            return

        if not device_info.get("intune_device_id"):
            logger.warning(
                f"Asset '{device_info['asset_name']}' has no Intune Device ID - "
                f"skipping remediation"
            )
            return

        logger.info(
            f"Device: {device_info['asset_name']} | "
            f"Platform: {device_info['platform']} | "
            f"Intune ID: {device_info['intune_device_id']}"
        )

        # Step 3: Analyze ticket for issue type
        analysis = TicketAnalyzer.analyze(
            ticket_info["subject"],
            ticket_info["description"],
            device_info["platform"]
        )

        logger.info(
            f"Analysis: {analysis['issue_type']} (confidence: {analysis['confidence']}) | "
            f"Actions: {analysis['actions']}"
        )

        # Step 4: Skip unsupported platforms (Android etc.)
        if device_info["platform"] == "Android":
            logger.info(f"Android device {device_info['asset_name']} - running diagnostic only")
            analysis["actions"] = ["diagnose_comprehensive"]

        # Step 5: Run remediation
        result = await run_remediation(
            device_info["intune_device_id"],
            analysis["actions"],
            device_info["platform"]
        )

        logger.info(
            f"Remediation complete for {display_id} | "
            f"Success: {result['overall_success']} | "
            f"Executed: {len(result['executed'])} | "
            f"Failed: {len(result['failed'])}"
        )

        # Step 6a: Post private technical report (IT agents only)
        private_html = RemediationNoteBuilder.build(
            display_id=display_id,
            ticket_info=ticket_info,
            device_info=device_info,
            analysis=analysis,
            remediation_result=result,
        )
        private_result = await client.post_note(display_id, private_html, is_private=True)
        if private_result.get("success"):
            logger.info(f"Private technical note posted on {display_id}")
        else:
            logger.error(f"Private note post failed on {display_id}: {private_result.get('error')}")

        # Step 6b: Post public user-facing reply
        user_html = RemediationNoteBuilder.build_user_reply(
            device_info=device_info,
            analysis=analysis,
            remediation_result=result,
        )
        user_result = await client.post_note(display_id, user_html, is_private=False)
        if user_result.get("success"):
            logger.info(f"User reply posted on {display_id}")
        else:
            logger.error(f"User reply post failed on {display_id}: {user_result.get('error')}")

    except HTTPException as e:
        logger.error(f"HTTP error processing ticket {display_id}: {e.detail}")
        # Post a failure note so the agent knows something went wrong
        try:
            client = get_atomicwork_client()
            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            err_html = (
                f'<div style="font-family:Arial,sans-serif;font-size:13px;">'
                f'<p style="background:#fef2f2;border-left:3px solid #dc2626;padding:8px 12px;color:#b91c1c;">'
                f'Automated remediation could not start for ticket {display_id}.<br>'
                f'Reason: {e.detail}<br>'
                f'<span style="font-size:11px;color:#9ca3af;">{ts}</span>'
                f'</p></div>'
            )
            await client.post_note(display_id, err_html, is_private=False)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Unexpected error processing ticket {display_id}: {str(e)}", exc_info=True)
        # Post a failure note
        try:
            client = get_atomicwork_client()
            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            err_html = (
                f'<div style="font-family:Arial,sans-serif;font-size:13px;">'
                f'<p style="background:#fef2f2;border-left:3px solid #dc2626;padding:8px 12px;color:#b91c1c;">'
                f'Automated remediation failed for ticket {display_id}.<br>'
                f'Error: {str(e)[:200]}<br>'
                f'<span style="font-size:11px;color:#9ca3af;">{ts}</span>'
                f'</p></div>'
            )
            await client.post_note(display_id, err_html, is_private=False)
        except Exception:
            pass


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/api/v1/webhook-info")
async def webhook_info():
    return {
        "service": "Intune Device Healer - Atomicwork Integration",
        "status": "running",
        "version": "2.0.0",
        "architecture": "Atomicwork webhook → Lambda → Atomicwork API → Intune remediation",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "health": "GET /health",
            "webhook": "POST /webhook/ticket  ← configure this in Atomicwork",
            "analyze": "POST /analyze-ticket",
            "remediate": "POST /execute-remediation",
            "ticket_info": "GET /ticket/{display_id}",
            "docs": "GET /docs"
        },
        "webhook_payload": {
            "display_id": "DWINC-7947",
            "event_type": "ticket_created"
        }
    }


@app.get("/health")
async def health():
    try:
        config = get_config()
        auth = get_authenticator()
        token = auth.get_access_token()

        # Also verify Atomicwork API key is configured
        aw_client = get_atomicwork_client()
        aw_configured = bool(aw_client.api_key)

        return {
            "status": "healthy",
            "intune_connection": "ok" if token else "failed",
            "atomicwork_api": "configured" if aw_configured else "missing ATOMICWORK_API_KEY",
            "azure_tenant": config.azure_tenant_id,
            "atomicwork_url": aw_client.base_url,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })


@app.post("/webhook/ticket", status_code=202)
async def webhook(payload: AtomicworkWebhookPayload, background_tasks: BackgroundTasks):
    """
    Receive Atomicwork ticket webhook and trigger automated remediation.

    Atomicwork should POST to this endpoint when a ticket is created/updated.
    Only the display_id is needed - all details are fetched from the Atomicwork API.

    Payload: { "display_id": "DWINC-7947", "event_type": "ticket_created" }
    Returns: 202 Accepted immediately. Remediation runs in background.
    """

    display_id = payload.display_id.strip().upper()
    event_type = payload.event_type or "ticket_created"

    logger.info(f"Webhook received: {display_id} ({event_type})")

    # Only process on ticket creation or updates (not deletions, closures, etc.)
    if event_type in ("ticket_created", "ticket_updated", "incident_created", "incident_updated"):
        background_tasks.add_task(process_ticket_background, display_id, event_type)
        queued = True
        message = "Ticket received. Fetching details from Atomicwork and queuing remediation."
    else:
        queued = False
        message = f"Event type '{event_type}' does not trigger remediation."

    return {
        "status": "accepted",
        "display_id": display_id,
        "event_type": event_type,
        "queued": queued,
        "message": message,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/ticket/{display_id}")
async def get_ticket_info(display_id: str):
    """
    Fetch and display parsed ticket + asset info from Atomicwork.
    Useful for testing and verifying the integration before enabling remediation.
    """
    try:
        client = get_atomicwork_client()
        ticket_data = await client.get_ticket(display_id.upper())
        ticket_info = client.extract_ticket_info(ticket_data)
        device_info = client.extract_device_info(ticket_data)

        # Run analysis if device found
        analysis = None
        if device_info:
            analysis = TicketAnalyzer.analyze(
                ticket_info["subject"],
                ticket_info["description"],
                device_info.get("platform", "Windows")
            )

        return {
            "display_id": display_id.upper(),
            "ticket": ticket_info,
            "device": device_info,
            "analysis": analysis,
            "would_remediate": bool(device_info and device_info.get("intune_device_id")),
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze-ticket")
async def analyze_ticket(request: AnalyzeRequest):
    """Analyze ticket text to predict issue type + actions (dry run, no API calls)"""
    analysis = TicketAnalyzer.analyze(request.subject, request.description, request.platform)
    return {
        "subject": request.subject,
        "platform": request.platform,
        "analysis": analysis,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/execute-remediation")
async def execute_remediation_endpoint(request: ManualRemediationRequest):
    """Manually trigger specific remediation actions on a device by Intune Device ID"""
    try:
        result = await run_remediation(request.device_id, request.actions, request.platform)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/devices")
async def list_devices():
    """List all Intune managed devices"""
    try:
        diag = get_diagnostic_tools()
        result = await diag.list_devices()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/fleet/health")
async def fleet_health():
    """Get fleet health dashboard"""
    try:
        monitoring = get_monitoring_tools()
        result = await monitoring.get_fleet_health_dashboard()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/auto-heal")
async def auto_heal_endpoint(request: AutoHealRequest):
    """
    Unified endpoint: Analyze ticket context and execute the best remediation actions.
    Example: "My CPU is slow" -> get_performance_diagnostics + cleanup_disk_space
    """
    try:
        # 1. Analyze context
        analysis = TicketAnalyzer.analyze(request.subject, request.description, request.platform)
        
        logger.info(
            f"Auto-Heal Request | Subject: {request.subject} | "
            f"Detected: {analysis['issue_type']} | Actions: {analysis['actions']}"
        )
        
        # 2. Execute remediation
        result = await run_remediation(request.device_id, analysis["actions"], request.platform)
        
        return {
            "analysis": analysis,
            "remediation": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Auto-heal failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
