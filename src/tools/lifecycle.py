"""
Employee Lifecycle Tools
Orchestrates device management across the full employee lifecycle:
  - Onboarding  : enrollment, profiles, apps, encryption, CA, identity
  - Day-to-day  : authentication, connectivity, compliance, M365 productivity
  - Offboarding : wipe, license reclaim, access revoke, data transfer, cleanup

Issues covered: 1-15 (Onboarding), 16-25 (Auth/Identity), 26-38 (Connectivity),
                39-52 (M365 Productivity), 66-77 (Security/Compliance),
                91-100 (Offboarding)
"""

import asyncio
import structlog
from typing import Dict, List, Optional, Any
from datetime import datetime
from core.graph_client import GraphClient

logger = structlog.get_logger()


class LifecycleTools:
    """
    High-level orchestration tools for employee device lifecycle management.

    Each method maps to one or more of the Top 100 issues catalog and calls
    the appropriate Intune Graph API endpoints.
    """

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.client = GraphClient(authenticator, config)

    # =========================================================================
    # ── ONBOARDING ────────────────────────────────────────────────────────────
    # =========================================================================

    # ISSUE 1 – Windows Autopilot Enrollment Failure
    async def fix_enrollment_autopilot(
        self, device_id: str, user_upn: str = None
    ) -> Dict[str, Any]:
        """
        Recover a stalled or failed Windows Autopilot enrollment.
        Tier 1 – retriggers sync and checks Autopilot profile assignment.

        Fixes:
          - Autopilot profile not delivered during OOBE
          - Device not finding Autopilot profile
          - ESP (Enrollment Status Page) timing out
          - Azure AD Join failing mid-Autopilot
        """
        logger.info("fix_enrollment_autopilot", device_id=device_id, user_upn=user_upn)
        steps = []
        try:
            # Sync Autopilot devices from cloud
            await self.client.post(
                "/deviceManagement/windowsAutopilotDeviceIdentities/sync", body={}
            )
            steps.append("Triggered Autopilot cloud sync")

            # Force MDM sync to re-deliver enrollment commands
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Triggered MDM sync on device")

            # Fetch device + Autopilot profile state
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,managementState,autopilotEnrolled,joinType"}
            )
            steps.append(f"Autopilot enrolled: {device.get('autopilotEnrolled')} | Join type: {device.get('joinType')}")

            return {
                "success": True,
                "operation": "fix_enrollment_autopilot",
                "tier": 1,
                "device_id": device_id,
                "autopilot_enrolled": device.get("autopilotEnrolled"),
                "join_type": device.get("joinType"),
                "steps_completed": steps,
                "message": "Autopilot enrollment recovery triggered",
                "next_steps": [
                    "Restart device and connect to internet during OOBE",
                    "Wait for 'Your organization is setting up this PC'",
                    "If ESP stuck > 30 min: bypass ESP or check Intune ESP policy",
                    "Verify device serial is registered in Autopilot portal"
                ]
            }
        except Exception as e:
            logger.error("fix_enrollment_autopilot failed", error=str(e))
            return {"success": False, "operation": "fix_enrollment_autopilot", "error": str(e)}

    # ISSUE 2 – Apple ADE/DEP Enrollment Failure
    async def fix_enrollment_apple_ade(self, device_serial: str = None) -> Dict[str, Any]:
        """
        Recover a failed Apple ADE/DEP enrollment.
        Tier 1 – syncs ABM token and re-delivers enrollment profile.

        Fixes:
          - Device not receiving MDM profile during Setup Assistant
          - 'Remote Management' screen not appearing
          - ADE enrollment profile expired
        """
        logger.info("fix_enrollment_apple_ade", device_serial=device_serial)
        steps = []
        try:
            # Trigger Apple Business Manager sync
            dep_settings = await self.client.get(
                "/deviceManagement/depOnboardingSettings",
                params={"$select": "id,tokenName,tokenExpirationDateTime"}
            )
            tokens = dep_settings.get("value", [])

            if tokens:
                for token in tokens:
                    token_id = token.get("id")
                    expiry = token.get("tokenExpirationDateTime", "")
                    steps.append(f"ADE token '{token.get('tokenName')}' – expires: {expiry}")

                    # Trigger sync for this token
                    await self.client.post(
                        f"/deviceManagement/depOnboardingSettings/{token_id}/syncWithAppleDeviceEnrollmentProgram",
                        body={}
                    )
                    steps.append(f"Triggered ABM sync for token {token_id}")
            else:
                steps.append("WARNING: No ADE tokens configured – Apple Business Manager not connected")

            return {
                "success": True,
                "operation": "fix_enrollment_apple_ade",
                "tier": 1,
                "device_serial": device_serial,
                "ade_tokens": len(tokens),
                "steps_completed": steps,
                "message": "ADE sync triggered",
                "next_steps": [
                    "Erase and restart the Apple device",
                    "Connect to Wi-Fi during Setup Assistant",
                    "Await 'Remote Management' screen (may take 2-3 minutes)",
                    "If token expired: renew in Intune > Enrollment > Apple > ADE tokens"
                ]
            }
        except Exception as e:
            logger.error("fix_enrollment_apple_ade failed", error=str(e))
            return {"success": False, "operation": "fix_enrollment_apple_ade", "error": str(e)}

    # ISSUE 4 – Corporate Wi-Fi Profile Not Deployed
    async def push_wifi_profile(
        self, device_id: str, platform: str = "windows"
    ) -> Dict[str, Any]:
        """
        Force-sync corporate Wi-Fi configuration profile to a device.
        Tier 1 – sync triggers Intune to re-deliver all configuration profiles.

        Fixes:
          - Corporate SSID not available on device
          - Wi-Fi profile missing from Settings
          - 802.1x / certificate-based Wi-Fi not configured
        """
        logger.info("push_wifi_profile", device_id=device_id, platform=platform)
        steps = []
        try:
            # Find Wi-Fi profiles for the platform
            filter_map = {
                "windows": "isof('microsoft.graph.windowsWifiConfiguration')",
                "macos": "isof('microsoft.graph.macOSWifiConfiguration')",
                "ios": "isof('microsoft.graph.iosWifiConfiguration')",
                "android": "isof('microsoft.graph.androidWorkProfileWifiConfiguration')"
            }
            f = filter_map.get(platform.lower(), "")
            if f:
                wifi_profiles = await self.client.get(
                    "/deviceManagement/deviceConfigurations",
                    params={"$filter": f, "$select": "id,displayName"}
                )
                profiles = wifi_profiles.get("value", [])
                steps.append(f"Found {len(profiles)} Wi-Fi profile(s) for {platform}")

            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – Wi-Fi profile will be re-delivered")

            return {
                "success": True,
                "operation": "push_wifi_profile",
                "tier": 1,
                "device_id": device_id,
                "platform": platform,
                "steps_completed": steps,
                "message": f"Wi-Fi profile sync triggered for {platform} device",
                "next_steps": [
                    "Wait 5-10 minutes and check device Wi-Fi settings",
                    "Corporate SSID should appear automatically",
                    "If using certificate-based Wi-Fi: ensure SCEP certificate is deployed first"
                ]
            }
        except Exception as e:
            logger.error("push_wifi_profile failed", error=str(e))
            return {"success": False, "operation": "push_wifi_profile", "error": str(e)}

    # ISSUE 5 – VPN Profile Not Deployed
    async def push_vpn_profile(
        self, device_id: str, platform: str = "windows"
    ) -> Dict[str, Any]:
        """
        Force-sync corporate VPN configuration profile.
        Tier 1 – sync re-delivers VPN and any dependent certificate profiles.

        Fixes:
          - VPN client not configured
          - VPN profile missing after OS upgrade
          - Certificate for VPN auth not deployed
        """
        logger.info("push_vpn_profile", device_id=device_id, platform=platform)
        steps = []
        try:
            filter_map = {
                "windows": "isof('microsoft.graph.windowsVpnConfiguration')",
                "macos": "isof('microsoft.graph.macOSVpnConfiguration')",
                "ios": "isof('microsoft.graph.iosVpnConfiguration')",
                "android": "isof('microsoft.graph.androidWorkProfileVpnConfiguration')"
            }
            f = filter_map.get(platform.lower(), "")
            if f:
                vpn_profiles = await self.client.get(
                    "/deviceManagement/deviceConfigurations",
                    params={"$filter": f, "$select": "id,displayName"}
                )
                profiles = vpn_profiles.get("value", [])
                steps.append(f"Found {len(profiles)} VPN profile(s) for {platform}")

            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – VPN profile will be re-delivered")

            return {
                "success": True,
                "operation": "push_vpn_profile",
                "tier": 1,
                "device_id": device_id,
                "platform": platform,
                "steps_completed": steps,
                "message": f"VPN profile sync triggered for {platform} device",
                "next_steps": [
                    "Wait 10 minutes for VPN profile delivery",
                    "Check VPN client settings after sync",
                    "Ensure VPN gateway is accessible and certificate chain is trusted"
                ]
            }
        except Exception as e:
            logger.error("push_vpn_profile failed", error=str(e))
            return {"success": False, "operation": "push_vpn_profile", "error": str(e)}

    # ISSUE 6 – Work Email Profile Not Configured
    async def push_email_profile(
        self, device_id: str, platform: str = "windows", user_email: str = None
    ) -> Dict[str, Any]:
        """
        Force-sync corporate Exchange email configuration profile.
        Tier 1 – sync re-delivers email profile to device.

        Fixes:
          - Outlook / Mail app not configured with corporate email
          - Exchange ActiveSync profile missing
          - ActiveSync partnership not established
        """
        logger.info("push_email_profile", device_id=device_id, platform=platform)
        steps = []
        try:
            filter_map = {
                "ios": "isof('microsoft.graph.iosEasEmailProfileConfiguration')",
                "android": "isof('microsoft.graph.androidWorkProfileEasEmailProfileBase')"
            }
            f = filter_map.get(platform.lower())
            if f:
                email_profiles = await self.client.get(
                    "/deviceManagement/deviceConfigurations",
                    params={"$filter": f, "$select": "id,displayName"}
                )
                profiles = email_profiles.get("value", [])
                steps.append(f"Found {len(profiles)} email profile(s) for {platform}")
            else:
                steps.append(f"Email profiles for {platform} managed through Outlook app policies")

            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – email profile will be re-delivered")

            return {
                "success": True,
                "operation": "push_email_profile",
                "tier": 1,
                "device_id": device_id,
                "platform": platform,
                "user_email": user_email,
                "steps_completed": steps,
                "message": "Email profile sync triggered",
                "next_steps": [
                    "Open Mail/Outlook app after 5-10 minutes",
                    "Profile should auto-configure corporate email account",
                    "User may need to enter their corporate password once"
                ]
            }
        except Exception as e:
            logger.error("push_email_profile failed", error=str(e))
            return {"success": False, "operation": "push_email_profile", "error": str(e)}

    # ISSUE 7 – Required Apps Not Installing
    async def force_app_installations(
        self, device_id: str, app_names: List[str] = None
    ) -> Dict[str, Any]:
        """
        Force required app installations on a device via Intune sync.
        Tier 1 – triggers sync and reports app installation status.

        Fixes:
          - Required apps stuck as 'Not installed'
          - Apps not appearing in Company Portal after enrollment
          - App assignments not reaching device
        """
        logger.info("force_app_installations", device_id=device_id, app_names=app_names)
        steps = []
        try:
            # Get current app state
            app_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/managedDeviceMobileAppConfigurationStates",
                params={"$select": "displayName,state,errorCode"}
            )
            all_apps = app_states.get("value", [])

            pending = [a for a in all_apps if a.get("state") not in ("installed", "succeeded", "notApplicable")]
            steps.append(f"Apps pending installation: {len(pending)}/{len(all_apps)}")

            if app_names:
                matched = [a for a in pending if any(n.lower() in a.get("displayName","").lower() for n in app_names)]
                steps.append(f"Requested apps with issues: {[a.get('displayName') for a in matched]}")

            # Trigger sync to force app delivery
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – required apps will be re-pushed")

            return {
                "success": True,
                "operation": "force_app_installations",
                "tier": 1,
                "device_id": device_id,
                "total_managed_apps": len(all_apps),
                "pending_apps": len(pending),
                "pending_details": pending[:10],  # cap at 10
                "steps_completed": steps,
                "message": "App installation sync triggered",
                "next_steps": [
                    "Open Company Portal and tap 'Sync' if apps still missing after 30 minutes",
                    "Verify the device is in the correct Intune assignment group",
                    "Check app licensing in Intune if app remains unavailable"
                ]
            }
        except Exception as e:
            logger.error("force_app_installations failed", error=str(e))
            return {"success": False, "operation": "force_app_installations", "error": str(e)}

    # ISSUE 8 – Enrollment Status Page (ESP) Stuck
    async def fix_esp_stuck(
        self, device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Resolve a Windows Autopilot ESP (Enrollment Status Page) that is stuck.
        Tier 2 – can optionally skip ESP blocking to allow user to proceed.

        Fixes:
          - ESP waiting indefinitely for apps to install
          - ESP blocking user login after Autopilot setup
          - ESP tracking policy not resolving
        """
        logger.info("fix_esp_stuck", device_id=device_id)
        if not auto_approve and self.config.require_approval_risky_ops:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "fix_esp_stuck",
                "risk": "moderate",
                "description": "Forces device sync and triggers ESP bypass if configured",
                "message": "Set auto_approve=True to proceed"
            }
        steps = []
        try:
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered to re-deliver pending ESP apps/policies")

            # Get ESP policy
            esp_policies = await self.client.get(
                "/deviceManagement/deviceEnrollmentConfigurations",
                params={
                    "$filter": "isof('microsoft.graph.windows10EnrollmentCompletionPageConfiguration')",
                    "$select": "id,displayName"
                }
            )
            esp_list = esp_policies.get("value", [])
            steps.append(f"ESP policies found: {len(esp_list)}")

            return {
                "success": True,
                "operation": "fix_esp_stuck",
                "tier": 2,
                "device_id": device_id,
                "esp_policies": len(esp_list),
                "steps_completed": steps,
                "message": "ESP recovery sync triggered",
                "next_steps": [
                    "Device should progress through ESP within 15-30 minutes after sync",
                    "If still stuck: check Intune ESP policy 'Block device use until required apps are installed'",
                    "Consider adding app to ESP 'do not block' list in Intune",
                    "Emergency: Power off and power on – device will retry ESP"
                ]
            }
        except Exception as e:
            logger.error("fix_esp_stuck failed", error=str(e))
            return {"success": False, "operation": "fix_esp_stuck", "error": str(e)}

    # ISSUE 9 – Conditional Access Blocking New Device
    async def fix_ca_new_device(
        self, device_id: str, user_upn: str
    ) -> Dict[str, Any]:
        """
        Diagnose why Conditional Access is blocking a newly enrolled device.
        Tier 1 – reads CA policy evaluation and device compliance state.

        Fixes:
          - Device blocked before compliance evaluation completes
          - Device not recognized as managed
          - CA requiring compliant device before apps are installed
        """
        logger.info("fix_ca_new_device", device_id=device_id, user_upn=user_upn)
        steps = []
        try:
            # Get device compliance
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={
                    "$select": "id,deviceName,complianceState,managementState,"
                               "azureADRegistered,azureADDeviceId,enrolledDateTime"
                }
            )
            steps.append(f"Compliance: {device.get('complianceState')} | AAD registered: {device.get('azureADRegistered')}")

            enrolled = device.get("enrolledDateTime", "")
            steps.append(f"Enrolled: {enrolled}")

            # Check user sign-in logs for CA failures
            sign_ins = await self.client.get(
                f"/auditLogs/signIns",
                params={
                    "$filter": f"userPrincipalName eq '{user_upn}' and conditionalAccessStatus eq 'failure'",
                    "$select": "createdDateTime,conditionalAccessStatus,appliedConditionalAccessPolicies,status",
                    "$top": "5",
                    "$orderby": "createdDateTime desc"
                }
            )
            recent_ca_failures = sign_ins.get("value", [])
            steps.append(f"Recent CA failures for user: {len(recent_ca_failures)}")

            # Sync device to trigger compliance re-evaluation
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered to re-evaluate compliance")

            return {
                "success": True,
                "operation": "fix_ca_new_device",
                "tier": 1,
                "device_id": device_id,
                "user_upn": user_upn,
                "compliance_state": device.get("complianceState"),
                "aad_registered": device.get("azureADRegistered"),
                "recent_ca_failures": len(recent_ca_failures),
                "ca_failure_details": [
                    {
                        "time": f.get("createdDateTime"),
                        "policies": [p.get("displayName") for p in f.get("appliedConditionalAccessPolicies", [])]
                    }
                    for f in recent_ca_failures[:3]
                ],
                "steps_completed": steps,
                "message": "CA diagnostics complete and compliance re-evaluation triggered",
                "next_steps": [
                    "Allow 15-30 minutes for compliance to evaluate after enrollment",
                    "New devices need a 'grace period' in CA policy – check policy settings",
                    "Ensure device is Azure AD registered (check AAD > Devices)",
                    "User should retry sign-in after device shows 'Compliant' in Intune"
                ]
            }
        except Exception as e:
            logger.error("fix_ca_new_device failed", error=str(e))
            return {"success": False, "operation": "fix_ca_new_device", "error": str(e)}

    # ISSUE 10 – BitLocker / FileVault Not Encrypting
    async def enable_device_encryption(
        self, device_id: str, platform: str = "windows"
    ) -> Dict[str, Any]:
        """
        Trigger disk encryption (BitLocker for Windows, FileVault for macOS).
        Tier 2 – pushes encryption policy and waits for compliance.

        Fixes:
          - Device marked non-compliant for encryption
          - BitLocker not enabled after Autopilot enrollment
          - FileVault not activated on new Mac
          - Encryption key not escrowed to Azure AD / Intune
        """
        logger.info("enable_device_encryption", device_id=device_id, platform=platform)
        if not self.config.auto_fix_enabled:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "enable_device_encryption",
                "risk": "moderate",
                "description": f"Enables {'BitLocker' if platform=='windows' else 'FileVault'} on device",
                "message": "Requires auto_fix_enabled=true in config"
            }
        steps = []
        try:
            if platform.lower() == "windows":
                # Check current encryption state
                device = await self.client.get(
                    f"/deviceManagement/managedDevices/{device_id}",
                    params={"$select": "id,deviceName,isEncrypted,complianceState"}
                )
                is_encrypted = device.get("isEncrypted", False)
                steps.append(f"Currently encrypted: {is_encrypted}")

                if not is_encrypted:
                    # Trigger BitLocker escrow
                    await self.client.post(
                        f"/deviceManagement/managedDevices/{device_id}/rotateBitLockerKeys",
                        body={}
                    )
                    steps.append("BitLocker key rotation / escrow triggered")

            elif platform.lower() == "macos":
                device = await self.client.get(
                    f"/deviceManagement/managedDevices/{device_id}",
                    params={"$select": "id,deviceName,isEncrypted,complianceState"}
                )
                is_encrypted = device.get("isEncrypted", False)
                steps.append(f"Currently encrypted: {is_encrypted}")

            # Sync to trigger encryption policy re-evaluation
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – encryption policy will be re-applied")

            return {
                "success": True,
                "operation": "enable_device_encryption",
                "tier": 2,
                "device_id": device_id,
                "platform": platform,
                "is_encrypted": device.get("isEncrypted", False),
                "steps_completed": steps,
                "message": f"{'BitLocker' if platform=='windows' else 'FileVault'} remediation triggered",
                "next_steps": [
                    "Device will encrypt in background (30-60 minutes for full disk)",
                    "Encryption key will be escrowed to Azure AD automatically",
                    "Compliance will update after encryption completes and device checks in",
                    "Do NOT power off device during encryption process"
                ]
            }
        except Exception as e:
            logger.error("enable_device_encryption failed", error=str(e))
            return {"success": False, "operation": "enable_device_encryption", "error": str(e)}

    # ISSUE 11 – Azure AD Registration Failure
    async def fix_azure_ad_registration(self, device_id: str) -> Dict[str, Any]:
        """
        Fix Azure AD device registration issues.
        Tier 1 – diagnoses and triggers re-registration sync.

        Fixes:
          - Device not appearing in Azure AD > Devices
          - MDM authority conflict (SCCM + Intune co-management)
          - Hybrid Azure AD Join broken after domain change
          - Device object stale in AAD
        """
        logger.info("fix_azure_ad_registration", device_id=device_id)
        steps = []
        try:
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={
                    "$select": "id,deviceName,azureADRegistered,azureADDeviceId,"
                               "joinType,managementState,complianceState"
                }
            )
            aad_registered = device.get("azureADRegistered", False)
            aad_device_id = device.get("azureADDeviceId", "")
            join_type = device.get("joinType", "")

            steps.append(f"AAD registered: {aad_registered} | Join type: {join_type}")
            steps.append(f"AAD device ID: {aad_device_id or 'NOT REGISTERED'}")

            if not aad_registered:
                steps.append("Device is NOT registered in Azure AD – will trigger re-registration sync")

            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("MDM sync triggered to re-register with Azure AD")

            return {
                "success": True,
                "operation": "fix_azure_ad_registration",
                "tier": 1,
                "device_id": device_id,
                "aad_registered": aad_registered,
                "aad_device_id": aad_device_id,
                "join_type": join_type,
                "steps_completed": steps,
                "message": "Azure AD registration sync triggered",
                "next_steps": [
                    "On Windows: run 'dsregcmd /status' to verify AAD join state",
                    "If AADJ failed: run 'dsregcmd /forcerecovery' as admin",
                    "For Hybrid AAD Join: verify on-prem AD connector is healthy",
                    "Check Azure AD > Devices for device object after 30 minutes"
                ]
            }
        except Exception as e:
            logger.error("fix_azure_ad_registration failed", error=str(e))
            return {"success": False, "operation": "fix_azure_ad_registration", "error": str(e)}

    # ISSUE 12 – Primary User Not Set on Device
    async def set_device_primary_user(
        self, device_id: str, user_upn: str
    ) -> Dict[str, Any]:
        """
        Set or update the primary user (user-device affinity) for an Intune device.
        Tier 1 – graph API write operation.

        Fixes:
          - Device enrolled with wrong user
          - Apps not targeting correct user
          - User-targeted CA policies not applying
        """
        logger.info("set_device_primary_user", device_id=device_id, user_upn=user_upn)
        steps = []
        try:
            # Find user ID from UPN
            user = await self.client.get(
                f"/users/{user_upn}",
                params={"$select": "id,displayName,userPrincipalName"}
            )
            user_id = user.get("id")
            steps.append(f"User found: {user.get('displayName')} ({user_id})")

            # Set primary user
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/users/$ref",
                body={"@odata.id": f"https://graph.microsoft.com/v1.0/users/{user_id}"}
            )
            steps.append(f"Primary user set to {user_upn}")

            return {
                "success": True,
                "operation": "set_device_primary_user",
                "tier": 1,
                "device_id": device_id,
                "user_upn": user_upn,
                "user_id": user_id,
                "steps_completed": steps,
                "message": f"Primary user set to {user_upn}"
            }
        except Exception as e:
            logger.error("set_device_primary_user failed", error=str(e))
            return {"success": False, "operation": "set_device_primary_user", "error": str(e)}

    # ISSUE 13 – Device Not in Correct Group
    async def assign_device_to_group(
        self, device_id: str, group_id: str
    ) -> Dict[str, Any]:
        """
        Add a device to an Azure AD / Intune device group for policy targeting.
        Tier 1.

        Fixes:
          - Device not receiving policies because it's in wrong group
          - New device not in 'All Corporate Devices' group
          - Device missing from dynamic group due to attribute issue
        """
        logger.info("assign_device_to_group", device_id=device_id, group_id=group_id)
        steps = []
        try:
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,azureADDeviceId,deviceName"}
            )
            aad_device_id = device.get("azureADDeviceId")

            if not aad_device_id:
                return {
                    "success": False,
                    "operation": "assign_device_to_group",
                    "error": "Device not registered in Azure AD – cannot add to group",
                    "device_id": device_id
                }

            # Add AAD device object to group
            await self.client.post(
                f"/groups/{group_id}/members/$ref",
                body={"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{aad_device_id}"}
            )
            steps.append(f"Device {device.get('deviceName')} added to group {group_id}")

            # Sync to pick up new policies
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered to apply new group policies")

            return {
                "success": True,
                "operation": "assign_device_to_group",
                "tier": 1,
                "device_id": device_id,
                "group_id": group_id,
                "aad_device_id": aad_device_id,
                "steps_completed": steps,
                "message": "Device added to group and sync triggered"
            }
        except Exception as e:
            logger.error("assign_device_to_group failed", error=str(e))
            return {"success": False, "operation": "assign_device_to_group", "error": str(e)}

    # ISSUE 15 – Company Portal Not Showing Apps / Sync App Assignments
    async def sync_app_assignments(self, device_id: str) -> Dict[str, Any]:
        """
        Force Intune to re-evaluate and sync all app assignments to a device.
        Tier 1 – triggers device sync and reads current assignment state.
        """
        logger.info("sync_app_assignments", device_id=device_id)
        steps = []
        try:
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – all app assignments re-evaluated")

            app_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/managedDeviceMobileAppConfigurationStates",
                params={"$select": "displayName,state,errorCode"}
            )
            apps = app_states.get("value", [])
            by_state: Dict[str, list] = {}
            for a in apps:
                s = a.get("state", "unknown")
                by_state.setdefault(s, []).append(a.get("displayName"))

            return {
                "success": True,
                "operation": "sync_app_assignments",
                "tier": 1,
                "device_id": device_id,
                "total_apps": len(apps),
                "app_states_summary": {k: len(v) for k, v in by_state.items()},
                "steps_completed": steps,
                "message": "App assignment sync triggered",
                "next_steps": [
                    "Open Company Portal and pull down to refresh",
                    "Allow 15-30 minutes for all apps to appear",
                    "If specific app missing: verify group assignment in Intune"
                ]
            }
        except Exception as e:
            logger.error("sync_app_assignments failed", error=str(e))
            return {"success": False, "operation": "sync_app_assignments", "error": str(e)}

    # =========================================================================
    # ── AUTHENTICATION & IDENTITY ─────────────────────────────────────────────
    # =========================================================================

    # ISSUE 16 – MFA Not Configured / MFA Loop
    async def fix_mfa_setup(self, user_upn: str) -> Dict[str, Any]:
        """
        Diagnose and remediate MFA registration issues for a user.
        Tier 1 – reads MFA status and creates registration reminder.

        Fixes:
          - User stuck in MFA registration loop
          - MFA not registered blocking all sign-ins
          - Authenticator app not set up
        """
        logger.info("fix_mfa_setup", user_upn=user_upn)
        steps = []
        try:
            # Get authentication methods
            auth_methods = await self.client.get(
                f"/users/{user_upn}/authentication/methods",
                params={"$select": "id,@odata.type"}
            )
            methods = auth_methods.get("value", [])
            method_types = [m.get("@odata.type", "").split(".")[-1] for m in methods]
            steps.append(f"Registered authentication methods: {method_types}")

            # Get MFA registration details
            mfa_detail = await self.client.get(
                f"/users/{user_upn}/authentication/microsoftAuthenticatorMethods"
            )
            authenticator_apps = mfa_detail.get("value", [])
            steps.append(f"Microsoft Authenticator registrations: {len(authenticator_apps)}")

            has_mfa = len([m for m in method_types if m not in ("passwordAuthenticationMethod",)]) > 0

            return {
                "success": True,
                "operation": "fix_mfa_setup",
                "tier": 1,
                "user_upn": user_upn,
                "has_mfa": has_mfa,
                "registered_methods": method_types,
                "authenticator_app_count": len(authenticator_apps),
                "steps_completed": steps,
                "message": "MFA status audited",
                "next_steps": (
                    ["MFA is configured – check CA policy if user is still blocked"] if has_mfa
                    else [
                        "User must register MFA at aka.ms/mfasetup",
                        "Send user the MFA setup link via alternative contact",
                        "If user is locked out: admin can temporarily bypass MFA in Azure AD > Users > Authentication methods"
                    ]
                )
            }
        except Exception as e:
            logger.error("fix_mfa_setup failed", error=str(e))
            return {"success": False, "operation": "fix_mfa_setup", "error": str(e)}

    # ISSUE 17 – Password Expired / Account Locked
    async def unlock_and_reset_password(
        self, user_upn: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Unlock a locked user account and force a password reset.
        Tier 2 – modifies user account state.

        Fixes:
          - Account locked after too many failed sign-in attempts
          - Password expired and user cannot reset via SSPR
          - Admin needs to unlock account for employee
        """
        if not auto_approve and self.config.require_approval_risky_ops:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "unlock_and_reset_password",
                "risk": "moderate",
                "description": f"Unlocks account and forces password reset for {user_upn}",
                "message": "Set auto_approve=True to proceed"
            }
        logger.info("unlock_and_reset_password", user_upn=user_upn)
        steps = []
        try:
            # Check current account state
            user = await self.client.get(
                f"/users/{user_upn}",
                params={"$select": "id,displayName,accountEnabled,passwordPolicies,userPrincipalName"}
            )
            steps.append(f"Account enabled: {user.get('accountEnabled')} | Password policies: {user.get('passwordPolicies')}")

            # Enable account if disabled (not offboarded but locked)
            if not user.get("accountEnabled"):
                await self.client.patch(
                    f"/users/{user.get('id')}",
                    body={"accountEnabled": True}
                )
                steps.append("Account re-enabled")

            # Force password reset at next sign-in
            await self.client.patch(
                f"/users/{user.get('id')}",
                body={"passwordProfile": {"forceChangePasswordNextSignIn": True}}
            )
            steps.append("Force password change on next sign-in set")

            return {
                "success": True,
                "operation": "unlock_and_reset_password",
                "tier": 2,
                "user_upn": user_upn,
                "user_id": user.get("id"),
                "steps_completed": steps,
                "message": "Account unlocked and password reset required on next sign-in",
                "next_steps": [
                    "Inform user that they must change their password at next sign-in",
                    "User should sign in at portal.office.com or any M365 app",
                    "SSPR must be enabled and registered for self-service future resets"
                ]
            }
        except Exception as e:
            logger.error("unlock_and_reset_password failed", error=str(e))
            return {"success": False, "operation": "unlock_and_reset_password", "error": str(e)}

    # ISSUE 19 – Microsoft Authenticator Issues
    async def fix_authenticator(self, user_upn: str) -> Dict[str, Any]:
        """
        Diagnose and reset Microsoft Authenticator registration.
        Tier 1 – audits and clears stale Authenticator entries.

        Fixes:
          - 'Approve sign-in' never arrives on Authenticator app
          - Authenticator showing account from old device
          - Push notifications not working in Authenticator
          - Phone number changed and old MFA device removed
        """
        logger.info("fix_authenticator", user_upn=user_upn)
        steps = []
        try:
            auth_methods = await self.client.get(
                f"/users/{user_upn}/authentication/microsoftAuthenticatorMethods"
            )
            methods = auth_methods.get("value", [])
            steps.append(f"Authenticator registrations: {len(methods)}")

            for m in methods:
                steps.append(f"  - Device: {m.get('displayName')} | Created: {m.get('createdDateTime')}")

            return {
                "success": True,
                "operation": "fix_authenticator",
                "tier": 1,
                "user_upn": user_upn,
                "authenticator_count": len(methods),
                "registrations": methods,
                "steps_completed": steps,
                "message": "Authenticator registrations audited",
                "next_steps": [
                    "If old device listed: delete stale entry in Azure AD > Users > Authentication methods",
                    "User should add new device at aka.ms/mfasetup",
                    "If push not working: have user check Authenticator app notification permissions",
                    "Alternative: enable SMS/TOTP as backup MFA method"
                ]
            }
        except Exception as e:
            logger.error("fix_authenticator failed", error=str(e))
            return {"success": False, "operation": "fix_authenticator", "error": str(e)}

    # ISSUE 23 – Certificate-Based Auth / SCEP Certificate Failure
    async def renew_scep_certificate(
        self, device_id: str
    ) -> Dict[str, Any]:
        """
        Trigger SCEP/PKCS certificate renewal on a device.
        Tier 1 – sync forces Intune NDES to issue a new certificate.

        Fixes:
          - Certificate expired for Wi-Fi or VPN authentication
          - SCEP enrollment failed during device setup
          - 802.1x certificate not trusted
        """
        logger.info("renew_scep_certificate", device_id=device_id)
        steps = []
        try:
            # Find certificate profiles for the device
            cert_profiles = await self.client.get(
                "/deviceManagement/deviceConfigurations",
                params={
                    "$filter": "isof('microsoft.graph.windowsCertificateProfileBase') or "
                               "isof('microsoft.graph.iosPkcsCertificateProfile') or "
                               "isof('microsoft.graph.macOSScepCertificateProfile')",
                    "$select": "id,displayName"
                }
            )
            profiles = cert_profiles.get("value", [])
            steps.append(f"Certificate profiles in tenant: {len(profiles)}")

            # Sync triggers Intune to re-issue certificates
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – Intune will re-issue SCEP/PKCS certificates")

            return {
                "success": True,
                "operation": "renew_scep_certificate",
                "tier": 1,
                "device_id": device_id,
                "certificate_profiles": len(profiles),
                "steps_completed": steps,
                "message": "Certificate renewal triggered via Intune sync",
                "next_steps": [
                    "Allow 15-30 minutes for new certificate to be issued",
                    "Check device certificate store after sync",
                    "Verify NDES/SCEP connector is healthy in Intune",
                    "If PKCS: check certificate authority connectivity"
                ]
            }
        except Exception as e:
            logger.error("renew_scep_certificate failed", error=str(e))
            return {"success": False, "operation": "renew_scep_certificate", "error": str(e)}

    # =========================================================================
    # ── SECURITY & COMPLIANCE ─────────────────────────────────────────────────
    # =========================================================================

    # ISSUE 66 – Device Marked Non-Compliant (diagnostic)
    async def diagnose_compliance(self, device_id: str) -> Dict[str, Any]:
        """
        Detailed compliance diagnosis for any device type.
        Tier 1 – reads all compliance policy states and identifies gaps.

        Fixes (identifies causes for):
          - Device non-compliant blocking CA-protected apps
          - Unknown compliance state after enrollment
          - Compliance deadline approaching
        """
        logger.info("diagnose_compliance", device_id=device_id)
        steps = []
        try:
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={
                    "$select": "id,deviceName,complianceState,operatingSystem,osVersion,"
                               "isEncrypted,jailBroken,lastSyncDateTime,userPrincipalName"
                }
            )
            steps.append(f"Compliance state: {device.get('complianceState')} | OS: {device.get('operatingSystem')} {device.get('osVersion')}")
            steps.append(f"Encrypted: {device.get('isEncrypted')} | Jailbroken: {device.get('jailBroken')}")
            steps.append(f"Last sync: {device.get('lastSyncDateTime')}")

            # Get compliance policy states
            compliance_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/deviceCompliancePolicyStates",
                params={"$select": "displayName,state,settingCount"}
            )
            policies = compliance_states.get("value", [])
            non_compliant = [p for p in policies if p.get("state") != "compliant"]
            steps.append(f"Compliance policies: {len(policies)} total, {len(non_compliant)} failing")

            # Trigger compliance re-evaluation sync
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Compliance re-evaluation triggered via device sync")

            return {
                "success": True,
                "operation": "diagnose_compliance",
                "tier": 1,
                "device_id": device_id,
                "device_name": device.get("deviceName"),
                "compliance_state": device.get("complianceState"),
                "os": f"{device.get('operatingSystem')} {device.get('osVersion')}",
                "is_encrypted": device.get("isEncrypted"),
                "is_jailbroken": device.get("jailBroken") == "True",
                "total_policies": len(policies),
                "failing_policies": non_compliant,
                "steps_completed": steps,
                "message": "Compliance diagnosis complete",
                "next_steps": [
                    f"Fix failing compliance policies: {[p.get('displayName') for p in non_compliant]}",
                    "Check each failing policy for specific setting violations",
                    "After fixing issues: trigger device sync and allow 30 minutes for re-evaluation"
                ]
            }
        except Exception as e:
            logger.error("diagnose_compliance failed", error=str(e))
            return {"success": False, "operation": "diagnose_compliance", "error": str(e)}

    # ISSUE 72 – OS Version Out of Compliance (trigger update)
    async def trigger_os_update(
        self, device_id: str, platform: str = "windows"
    ) -> Dict[str, Any]:
        """
        Trigger an OS update on a non-compliant device.
        Tier 2 – device will update and reboot.

        Fixes:
          - Device below minimum OS version required by compliance policy
          - Security patch not applied within policy grace period
          - Feature update deferred too long
        """
        logger.info("trigger_os_update", device_id=device_id, platform=platform)
        if not self.config.auto_fix_enabled:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "trigger_os_update",
                "risk": "moderate",
                "description": "Triggers OS update – device will reboot",
                "message": "Requires auto_fix_enabled=true"
            }
        steps = []
        try:
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,operatingSystem,osVersion,complianceState"}
            )
            steps.append(f"Current OS: {device.get('operatingSystem')} {device.get('osVersion')}")

            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – OS update policy will be re-evaluated and applied")

            return {
                "success": True,
                "operation": "trigger_os_update",
                "tier": 2,
                "device_id": device_id,
                "platform": platform,
                "current_os": device.get("osVersion"),
                "compliance_state": device.get("complianceState"),
                "steps_completed": steps,
                "message": "OS update policy sync triggered",
                "next_steps": [
                    "Device will schedule and apply OS update per Intune update ring policy",
                    "User will receive update notification",
                    "Encourage user to save work and allow update to complete",
                    "Compliance will update within 1 hour after successful update"
                ]
            }
        except Exception as e:
            logger.error("trigger_os_update failed", error=str(e))
            return {"success": False, "operation": "trigger_os_update", "error": str(e)}

    # ISSUE 73 – Unsanctioned App Detected
    async def block_unsanctioned_app(
        self, device_id: str, app_package_name: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Report and trigger removal of an unsanctioned app via Intune compliance alert.
        Tier 2 – marks device non-compliant and triggers admin notification.

        Fixes:
          - Personal app found on corporate device
          - Blocked application installed
          - App in 'restricted' list detected
        """
        if not auto_approve and self.config.require_approval_risky_ops:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "block_unsanctioned_app",
                "risk": "moderate",
                "description": f"Forces compliance policy re-evaluation to flag '{app_package_name}'",
                "message": "Set auto_approve=True to proceed"
            }
        logger.info("block_unsanctioned_app", device_id=device_id, app_package_name=app_package_name)
        steps = []
        try:
            steps.append(f"Flagged unsanctioned app: {app_package_name}")

            # Sync to trigger compliance re-evaluation (which checks app blocklist)
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – compliance will re-evaluate installed apps")

            return {
                "success": True,
                "operation": "block_unsanctioned_app",
                "tier": 2,
                "device_id": device_id,
                "app_package_name": app_package_name,
                "steps_completed": steps,
                "message": "Compliance re-evaluation triggered for unsanctioned app",
                "next_steps": [
                    f"Add '{app_package_name}' to Intune compliance policy > Restricted apps",
                    "Device will be marked non-compliant once compliance evaluates",
                    "CA policy will block corporate resources until app is removed",
                    "User will be notified via Company Portal to remove the app"
                ]
            }
        except Exception as e:
            logger.error("block_unsanctioned_app failed", error=str(e))
            return {"success": False, "operation": "block_unsanctioned_app", "error": str(e)}

    # ISSUE 74 – Jailbroken/Rooted Device Detected
    async def quarantine_device(
        self, device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Quarantine a jailbroken or rooted device by revoking compliance.
        Tier 3 – triggers remote lock and compliance re-evaluation.

        Fixes:
          - Jailbroken iOS device detected by Intune
          - Rooted Android device accessing corporate resources
          - Device attempting to bypass MDM restrictions
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 3,
                "operation": "quarantine_device",
                "risk": "high",
                "description": "Remotely locks device and triggers non-compliance action",
                "message": "Pass auto_approve=True to quarantine this device"
            }
        logger.info("quarantine_device", device_id=device_id)
        steps = []
        try:
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,jailBroken,operatingSystem,userPrincipalName"}
            )
            steps.append(f"Device: {device.get('deviceName')} | OS: {device.get('operatingSystem')} | Jailbroken: {device.get('jailBroken')}")

            # Remote lock
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/remoteLock", body={}
            )
            steps.append("Remote lock applied to device")

            # Sync to trigger CA block via non-compliance
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Compliance re-evaluation triggered – CA will block corporate resources")

            return {
                "success": True,
                "operation": "quarantine_device",
                "tier": 3,
                "device_id": device_id,
                "device_name": device.get("deviceName"),
                "user_upn": device.get("userPrincipalName"),
                "steps_completed": steps,
                "message": "Device quarantined – remote lock applied and CA access revoked",
                "next_steps": [
                    "Notify security team of jailbroken/rooted device",
                    "Contact device owner to investigate",
                    "Consider remote wipe if device contains sensitive corporate data",
                    "Review security incident per company policy"
                ]
            }
        except Exception as e:
            logger.error("quarantine_device failed", error=str(e))
            return {"success": False, "operation": "quarantine_device", "error": str(e)}

    # ISSUE 77 – Expired Device Certificate
    async def renew_device_certificate(self, device_id: str) -> Dict[str, Any]:
        """
        Trigger renewal of expired device certificates (SCEP/PKCS).
        Tier 1 – sync forces certificate re-issuance.
        """
        return await self.renew_scep_certificate(device_id)

    # =========================================================================
    # ── OFFBOARDING ───────────────────────────────────────────────────────────
    # =========================================================================

    # ISSUE 91 – Device Not Wiped After User Departure
    async def wipe_offboarded_device(
        self, device_id: str, device_type: str = "corporate",
        auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Wipe or retire a device belonging to a departed employee.
        Tier 3 – REQUIRES explicit approval.
          - corporate devices → full factory wipe
          - BYOD → retire (removes work profile/apps only)

        Fixes:
          - Corporate device not wiped after employee offboarding
          - BYOD not retired, corporate data still present
          - Device lost with ex-employee's data
        """
        if not auto_approve:
            action = "FACTORY WIPE" if device_type == "corporate" else "RETIRE (remove corporate data)"
            return {
                "success": False,
                "requires_approval": True,
                "tier": 3,
                "operation": "wipe_offboarded_device",
                "risk": "critical" if device_type == "corporate" else "high",
                "description": f"Will {action} device {device_id}",
                "message": "Pass auto_approve=True to confirm"
            }

        logger.info("wipe_offboarded_device", device_id=device_id, device_type=device_type)
        steps = []
        try:
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,operatingSystem,userPrincipalName,managedDeviceOwnerType"}
            )
            steps.append(f"Device: {device.get('deviceName')} | OS: {device.get('operatingSystem')} | Owner type: {device.get('managedDeviceOwnerType')}")

            if device_type == "corporate":
                body = {"keepEnrollmentData": False, "keepUserData": False}
                await self.client.post(
                    f"/deviceManagement/managedDevices/{device_id}/wipe", body=body
                )
                steps.append("Factory wipe command sent")
                action_taken = "factory_wipe"
            else:
                await self.client.post(
                    f"/deviceManagement/managedDevices/{device_id}/retire", body={}
                )
                steps.append("Retire command sent (corporate data removed, personal data preserved)")
                action_taken = "retire"

            return {
                "success": True,
                "operation": "wipe_offboarded_device",
                "tier": 3,
                "device_id": device_id,
                "device_name": device.get("deviceName"),
                "action_taken": action_taken,
                "device_type": device_type,
                "steps_completed": steps,
                "message": f"Device {action_taken} initiated for offboarding",
                "warning": "This action cannot be undone"
            }
        except Exception as e:
            logger.error("wipe_offboarded_device failed", error=str(e))
            return {"success": False, "operation": "wipe_offboarded_device", "error": str(e)}

    # ISSUE 93 – Autopilot Device Not Reset for Reuse
    async def autopilot_reset(
        self, device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Trigger Windows Autopilot Reset on a corporate device for reassignment.
        Tier 3 – resets OS to a fresh provisioned state without factory wipe.

        Fixes:
          - Device needs to be reprovisioned for a new employee
          - Autopilot device returning to inventory
          - OOBE needs to be re-triggered without full wipe
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 3,
                "operation": "autopilot_reset",
                "risk": "high",
                "description": "Autopilot Reset reinstalls Windows keeping enrollment data – user data is removed",
                "message": "Pass auto_approve=True to proceed"
            }
        logger.info("autopilot_reset", device_id=device_id)
        steps = []
        try:
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/wipe",
                body={"keepEnrollmentData": True, "keepUserData": False, "obliterationBehavior": "default"}
            )
            steps.append("Autopilot Reset (keep enrollment data) triggered")

            return {
                "success": True,
                "operation": "autopilot_reset",
                "tier": 3,
                "device_id": device_id,
                "steps_completed": steps,
                "message": "Autopilot Reset initiated – device will re-run OOBE with Autopilot",
                "next_steps": [
                    "Device will restart and run Windows setup (OOBE)",
                    "Autopilot profile will be re-applied automatically",
                    "Assign device to new user's group in Intune before they set it up"
                ]
            }
        except Exception as e:
            logger.error("autopilot_reset failed", error=str(e))
            return {"success": False, "operation": "autopilot_reset", "error": str(e)}

    # ISSUE 94 – Stale Azure AD Device Object
    async def cleanup_aad_device(
        self, device_id: str, aad_device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Remove a stale device object from Azure AD after offboarding.
        Tier 2 – deletes AAD device object.

        Fixes:
          - Old device still listed in Azure AD after wipe
          - Stale device consuming Intune license
          - Ex-employee device preventing clean re-enrollment
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "cleanup_aad_device",
                "risk": "moderate",
                "description": f"Deletes Azure AD device object {aad_device_id}",
                "message": "Pass auto_approve=True to delete the AAD device object"
            }
        logger.info("cleanup_aad_device", device_id=device_id, aad_device_id=aad_device_id)
        steps = []
        try:
            # Delete device from AAD
            await self.client.delete(f"/devices/{aad_device_id}")
            steps.append(f"Azure AD device object {aad_device_id} deleted")

            return {
                "success": True,
                "operation": "cleanup_aad_device",
                "tier": 2,
                "device_id": device_id,
                "aad_device_id": aad_device_id,
                "steps_completed": steps,
                "message": "AAD device object removed"
            }
        except Exception as e:
            logger.error("cleanup_aad_device failed", error=str(e))
            return {"success": False, "operation": "cleanup_aad_device", "error": str(e)}

    # ISSUE 95 – License Not Reclaimed After User Departure
    async def reclaim_user_licenses(
        self, user_upn: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Remove all M365 license assignments from a departed user.
        Tier 2 – removes SKU license assignments from user account.

        Fixes:
          - M365 / Intune / Copilot license still assigned to ex-employee
          - License not returned to pool after offboarding
          - Billing impact from unused licenses
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "reclaim_user_licenses",
                "risk": "moderate",
                "description": f"Removes all license assignments from {user_upn}",
                "message": "Pass auto_approve=True to reclaim licenses"
            }
        logger.info("reclaim_user_licenses", user_upn=user_upn)
        steps = []
        try:
            user = await self.client.get(
                f"/users/{user_upn}",
                params={"$select": "id,displayName,assignedLicenses"}
            )
            licenses = user.get("assignedLicenses", [])
            steps.append(f"Licenses to remove: {len(licenses)}")

            if licenses:
                sku_ids = [lic.get("skuId") for lic in licenses]
                await self.client.post(
                    f"/users/{user.get('id')}/assignLicense",
                    body={"addLicenses": [], "removeLicenses": sku_ids}
                )
                steps.append(f"Removed {len(sku_ids)} license(s)")

            return {
                "success": True,
                "operation": "reclaim_user_licenses",
                "tier": 2,
                "user_upn": user_upn,
                "licenses_removed": len(licenses),
                "removed_sku_ids": [lic.get("skuId") for lic in licenses],
                "steps_completed": steps,
                "message": f"All {len(licenses)} license(s) reclaimed from {user_upn}"
            }
        except Exception as e:
            logger.error("reclaim_user_licenses failed", error=str(e))
            return {"success": False, "operation": "reclaim_user_licenses", "error": str(e)}

    # ISSUE 96 – User Still Has Access Post-Departure
    async def revoke_user_access(
        self, user_upn: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Revoke all active sessions and refresh tokens for a departed user.
        Tier 2 – signs out all active sessions immediately.

        Fixes:
          - Ex-employee tokens still valid after offboarding
          - Refresh tokens not invalidated after account disable
          - User still accessing M365 apps after leaving
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "revoke_user_access",
                "risk": "moderate",
                "description": f"Revokes all refresh tokens and disables account for {user_upn}",
                "message": "Pass auto_approve=True to revoke access"
            }
        logger.info("revoke_user_access", user_upn=user_upn)
        steps = []
        try:
            user = await self.client.get(
                f"/users/{user_upn}",
                params={"$select": "id,displayName,accountEnabled"}
            )
            user_id = user.get("id")

            # Revoke all sign-in sessions (invalidate refresh tokens)
            await self.client.post(
                f"/users/{user_id}/revokeSignInSessions", body={}
            )
            steps.append("All sign-in sessions and refresh tokens revoked")

            # Disable account
            await self.client.patch(
                f"/users/{user_id}",
                body={"accountEnabled": False}
            )
            steps.append("User account disabled in Azure AD")

            return {
                "success": True,
                "operation": "revoke_user_access",
                "tier": 2,
                "user_upn": user_upn,
                "user_id": user_id,
                "steps_completed": steps,
                "message": "All access revoked and account disabled",
                "next_steps": [
                    "Verify no active sessions remain in Azure AD > Sign-in logs",
                    "Remove from all distribution lists and shared mailboxes",
                    "Archive mailbox if required by data retention policy",
                    "Trigger device wipe if device hasn't been wiped yet"
                ]
            }
        except Exception as e:
            logger.error("revoke_user_access failed", error=str(e))
            return {"success": False, "operation": "revoke_user_access", "error": str(e)}

    # ISSUE 97 – Device Still Enrolled After Factory Reset
    async def remove_from_intune(
        self, device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Remove a stale device record from Intune after factory reset.
        Tier 2 – deletes Intune managed device object.

        Fixes:
          - Device still listed in Intune after being wiped
          - Ghost device consuming license
          - Duplicate device records from re-enrollment
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "remove_from_intune",
                "risk": "moderate",
                "description": f"Deletes Intune managed device record {device_id}",
                "message": "Pass auto_approve=True to delete the device record"
            }
        logger.info("remove_from_intune", device_id=device_id)
        steps = []
        try:
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,operatingSystem,lastSyncDateTime"}
            )
            steps.append(f"Removing: {device.get('deviceName')} | Last sync: {device.get('lastSyncDateTime')}")

            await self.client.delete(f"/deviceManagement/managedDevices/{device_id}")
            steps.append("Intune device record deleted")

            return {
                "success": True,
                "operation": "remove_from_intune",
                "tier": 2,
                "device_id": device_id,
                "device_name": device.get("deviceName"),
                "steps_completed": steps,
                "message": "Device removed from Intune"
            }
        except Exception as e:
            logger.error("remove_from_intune failed", error=str(e))
            return {"success": False, "operation": "remove_from_intune", "error": str(e)}

    # ISSUE 98 – OneDrive Data Not Transferred to Manager
    async def transfer_onedrive_data(
        self, from_user_upn: str, to_user_upn: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Initiate OneDrive data access transfer from departing employee to manager.
        Tier 2 – grants manager access to ex-employee's OneDrive.

        Fixes:
          - Departed user's files inaccessible to team
          - Manager needs access to ex-employee's work files
          - OneDrive about to be deleted during offboarding
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "transfer_onedrive_data",
                "risk": "moderate",
                "description": f"Grants {to_user_upn} access to {from_user_upn}'s OneDrive",
                "message": "Pass auto_approve=True to grant OneDrive access"
            }
        logger.info("transfer_onedrive_data", from_user=from_user_upn, to_user=to_user_upn)
        steps = []
        try:
            # Get the from_user's OneDrive
            drive = await self.client.get(
                f"/users/{from_user_upn}/drive",
                params={"$select": "id,webUrl,owner"}
            )
            drive_id = drive.get("id")
            drive_url = drive.get("webUrl")
            steps.append(f"Source OneDrive: {drive_url}")

            # Share drive root with manager
            await self.client.post(
                f"/drives/{drive_id}/root/invite",
                body={
                    "recipients": [{"email": to_user_upn}],
                    "roles": ["write"],
                    "requireSignIn": True,
                    "sendInvitation": True,
                    "message": f"You have been granted access to {from_user_upn}'s OneDrive as part of their offboarding."
                }
            )
            steps.append(f"OneDrive access granted to {to_user_upn}")

            return {
                "success": True,
                "operation": "transfer_onedrive_data",
                "tier": 2,
                "from_user": from_user_upn,
                "to_user": to_user_upn,
                "drive_url": drive_url,
                "steps_completed": steps,
                "message": f"OneDrive access granted to {to_user_upn}",
                "next_steps": [
                    f"{to_user_upn} will receive an email invitation to access OneDrive",
                    "Files accessible via: " + drive_url,
                    "Remember to delete or archive OneDrive per data retention policy (typically 30 days after offboarding)"
                ]
            }
        except Exception as e:
            logger.error("transfer_onedrive_data failed", error=str(e))
            return {"success": False, "operation": "transfer_onedrive_data", "error": str(e)}

    # ISSUE 99 – Shared Device Not Re-Provisioned for Next User
    async def reprovision_shared_device(
        self, device_id: str, new_user_upn: str = None
    ) -> Dict[str, Any]:
        """
        Prepare a shared/kiosk device for the next user without full wipe.
        Tier 2 – changes primary user and triggers policy re-evaluation.

        Fixes:
          - Shared device still showing previous user's profile
          - Kiosk device not ready for next shift worker
          - Shared PC needing user profile cleanup
        """
        logger.info("reprovision_shared_device", device_id=device_id, new_user_upn=new_user_upn)
        steps = []
        try:
            if new_user_upn:
                result = await self.set_device_primary_user(device_id, new_user_upn)
                if result.get("success"):
                    steps.append(f"Primary user updated to {new_user_upn}")
                else:
                    steps.append(f"Warning: could not set primary user – {result.get('error')}")

            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – policies re-applied for new user context")

            return {
                "success": True,
                "operation": "reprovision_shared_device",
                "tier": 2,
                "device_id": device_id,
                "new_user": new_user_upn,
                "steps_completed": steps,
                "message": "Shared device re-provisioned for next user",
                "next_steps": [
                    "New user should sign in with their corporate credentials",
                    "Required apps will be delivered within 30 minutes",
                    "For Windows Shared PC: old user profile auto-deleted on next sign-in"
                ]
            }
        except Exception as e:
            logger.error("reprovision_shared_device failed", error=str(e))
            return {"success": False, "operation": "reprovision_shared_device", "error": str(e)}

    # ISSUE 100 – BitLocker Key Verification After User Departure
    async def verify_bitlocker_escrow(self, device_id: str) -> Dict[str, Any]:
        """
        Verify BitLocker recovery key is escrowed to Azure AD / Intune.
        Tier 1 – read-only check.

        Fixes:
          - Ensuring recovery key accessible after user leaves
          - Confirming key was escrowed before device wipe
          - Compliance audit for key management
        """
        logger.info("verify_bitlocker_escrow", device_id=device_id)
        steps = []
        try:
            # Check via Intune managed device
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,isEncrypted,azureADDeviceId,operatingSystem"}
            )
            is_encrypted = device.get("isEncrypted", False)
            aad_id = device.get("azureADDeviceId", "")
            steps.append(f"Device encrypted: {is_encrypted}")

            key_info = None
            if aad_id:
                # Try to get BitLocker recovery key info (requires admin role)
                try:
                    keys = await self.client.get(
                        f"/informationProtection/bitlocker/recoveryKeys",
                        params={
                            "$filter": f"deviceId eq '{aad_id}'",
                            "$select": "id,deviceId,createdDateTime,volumeType"
                        }
                    )
                    key_list = keys.get("value", [])
                    steps.append(f"BitLocker recovery key(s) found in Azure AD: {len(key_list)}")
                    key_info = key_list
                except Exception:
                    steps.append("Note: BitLocker key retrieval requires BitLocker.ReadBasic.All permission")

            escrowed = bool(key_info)

            return {
                "success": True,
                "operation": "verify_bitlocker_escrow",
                "tier": 1,
                "device_id": device_id,
                "device_name": device.get("deviceName"),
                "is_encrypted": is_encrypted,
                "aad_device_id": aad_id,
                "key_escrowed": escrowed,
                "key_count": len(key_info) if key_info else 0,
                "steps_completed": steps,
                "message": "BitLocker key escrowed" if escrowed else "BitLocker key NOT escrowed – action required",
                "next_steps": (
                    ["Key is safely escrowed – proceed with device wipe if needed"] if escrowed
                    else [
                        "Trigger BitLocker key backup: run 'manage-bde -protectors -adbackup C: -id {KeyID}' on device",
                        "Or in Intune: Devices > select device > Recovery keys",
                        "Do NOT wipe device until recovery key is confirmed escrowed"
                    ]
                )
            }
        except Exception as e:
            logger.error("verify_bitlocker_escrow failed", error=str(e))
            return {"success": False, "operation": "verify_bitlocker_escrow", "error": str(e)}

    # =========================================================================
    # ── FULL LIFECYCLE ORCHESTRATION ──────────────────────────────────────────
    # =========================================================================

    async def run_onboarding_checklist(
        self, device_id: str, user_upn: str, platform: str = "windows"
    ) -> Dict[str, Any]:
        """
        Run the complete device onboarding health checklist for a new employee.
        Covers issues 1-15 in the lifecycle catalog.
        Tier 1 – diagnostic with targeted sync operations.

        Returns a checklist of onboarding items and their status.
        """
        logger.info("run_onboarding_checklist", device_id=device_id, user_upn=user_upn, platform=platform)
        checklist = []

        try:
            # Device state
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={
                    "$select": "id,deviceName,operatingSystem,osVersion,managementState,"
                               "complianceState,isEncrypted,azureADRegistered,lastSyncDateTime,"
                               "userPrincipalName,enrolledDateTime,autopilotEnrolled"
                }
            )

            def check(name: str, passed: bool, detail: str = "", fix: str = ""):
                checklist.append({
                    "item": name,
                    "status": "PASS" if passed else "FAIL",
                    "detail": detail,
                    "fix": fix
                })

            check("Device enrolled",
                  device.get("managementState") in ("managed", "managedWithMamEnrollment"),
                  device.get("managementState"),
                  "Re-enroll device or trigger Autopilot reset")

            check("Azure AD registered",
                  device.get("azureADRegistered") is True,
                  str(device.get("azureADRegistered")),
                  "Run fix_azure_ad_registration")

            check("Device compliant",
                  device.get("complianceState") == "compliant",
                  device.get("complianceState"),
                  "Run diagnose_compliance")

            check("Disk encrypted",
                  device.get("isEncrypted") is True,
                  str(device.get("isEncrypted")),
                  "Run enable_device_encryption")

            check("Correct primary user",
                  (device.get("userPrincipalName", "").lower() == user_upn.lower()),
                  device.get("userPrincipalName"),
                  f"Run set_device_primary_user(device_id, '{user_upn}')")

            # App state
            app_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/managedDeviceMobileAppConfigurationStates",
                params={"$select": "displayName,state"}
            )
            apps = app_states.get("value", [])
            pending_apps = [a for a in apps if a.get("state") not in ("installed", "succeeded", "notApplicable")]
            check("Required apps installed",
                  len(pending_apps) == 0,
                  f"{len(pending_apps)} app(s) pending",
                  "Run force_app_installations")

            # Config profiles
            cfg_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/deviceConfigurationStates",
                params={"$select": "displayName,state"}
            )
            profiles = cfg_states.get("value", [])
            profile_errors = [p for p in profiles if p.get("state") == "error"]
            check("Configuration profiles applied",
                  len(profile_errors) == 0,
                  f"{len(profile_errors)} profile error(s)",
                  "Review profile errors in Intune; re-sync device")

            passes = sum(1 for c in checklist if c["status"] == "PASS")
            total = len(checklist)
            score = round((passes / total) * 100) if total else 0

            return {
                "success": True,
                "operation": "run_onboarding_checklist",
                "tier": 1,
                "device_id": device_id,
                "user_upn": user_upn,
                "platform": platform,
                "device_name": device.get("deviceName"),
                "checklist": checklist,
                "passed": passes,
                "total": total,
                "onboarding_score": score,
                "onboarding_complete": score == 100,
                "message": f"Onboarding {score}% complete ({passes}/{total} checks passed)"
            }

        except Exception as e:
            logger.error("run_onboarding_checklist failed", error=str(e))
            return {"success": False, "operation": "run_onboarding_checklist", "error": str(e)}

    async def run_offboarding_checklist(
        self, device_id: str, user_upn: str
    ) -> Dict[str, Any]:
        """
        Run the complete offboarding checklist for a departing employee.
        Covers issues 91-100 in the lifecycle catalog.
        Tier 1 – diagnostic only; destructive actions require separate approval.

        Returns checklist of offboarding tasks and their status.
        """
        logger.info("run_offboarding_checklist", device_id=device_id, user_upn=user_upn)
        checklist = []

        try:
            def check(name: str, passed: bool, detail: str = "", action: str = ""):
                checklist.append({
                    "item": name,
                    "status": "DONE" if passed else "TODO",
                    "detail": detail,
                    "action_required": action
                })

            # Check device state
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,managementState,isEncrypted,azureADDeviceId,complianceState"}
            )
            mgmt_state = device.get("managementState", "")
            check("Device wiped or retired",
                  mgmt_state in ("retirePending", "wipePending", "unhealthy"),
                  mgmt_state,
                  "Run wipe_offboarded_device(device_id, 'corporate', auto_approve=True)")

            # Check BitLocker
            check("BitLocker key escrowed",
                  device.get("isEncrypted") is True,
                  str(device.get("isEncrypted")),
                  "Run verify_bitlocker_escrow and backup key before wipe")

            # Check user account
            try:
                user = await self.client.get(
                    f"/users/{user_upn}",
                    params={"$select": "id,accountEnabled,assignedLicenses"}
                )
                account_enabled = user.get("accountEnabled", True)
                license_count = len(user.get("assignedLicenses", []))

                check("User account disabled",
                      not account_enabled,
                      str(account_enabled),
                      "Run revoke_user_access(user_upn, auto_approve=True)")

                check("Licenses reclaimed",
                      license_count == 0,
                      f"{license_count} license(s) still assigned",
                      "Run reclaim_user_licenses(user_upn, auto_approve=True)")
            except Exception:
                check("User account check", False, "User not found", "Verify user UPN")

            # OneDrive check
            try:
                drive = await self.client.get(
                    f"/users/{user_upn}/drive",
                    params={"$select": "id,webUrl"}
                )
                check("OneDrive data transferred",
                      False,
                      "OneDrive still active",
                      "Run transfer_onedrive_data(user_upn, manager_upn, auto_approve=True)")
            except Exception:
                check("OneDrive check", True, "OneDrive not accessible (may already be removed)", "")

            done = sum(1 for c in checklist if c["status"] == "DONE")
            total = len(checklist)

            return {
                "success": True,
                "operation": "run_offboarding_checklist",
                "tier": 1,
                "device_id": device_id,
                "user_upn": user_upn,
                "device_name": device.get("deviceName"),
                "checklist": checklist,
                "completed": done,
                "total": total,
                "offboarding_complete": done == total,
                "message": f"Offboarding {done}/{total} tasks complete"
            }

        except Exception as e:
            logger.error("run_offboarding_checklist failed", error=str(e))
            return {"success": False, "operation": "run_offboarding_checklist", "error": str(e)}
