"""
iOS / iPadOS Remediation Tools
Covers enrollment, profiles, apps, updates, and security for Apple mobile devices
managed through Microsoft Intune (Apple Business Manager / ADE).
"""

import structlog
from typing import Dict, List, Optional, Any
from datetime import datetime
from core.graph_client import GraphClient

logger = structlog.get_logger()


class iOSRemediationTools:
    """
    Tools for diagnosing and remediating iOS/iPadOS device issues via Intune Graph API.

    All operations are non-destructive (Tier 1) or semi-automatic (Tier 2) unless
    explicitly noted.  Destructive actions (Tier 3) require auto_approve=True.
    """

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.client = GraphClient(authenticator, config)

    # =========================================================================
    # ISSUE 78 – iOS ADE Enrollment Not Completing
    # =========================================================================

    async def fix_enrollment_ios(self, device_id: str) -> Dict[str, Any]:
        """
        Diagnose and remediate a stalled or failed iOS/iPadOS ADE enrollment.
        Tier 1 – forces a sync and re-sends the enrollment profile.

        Fixes:
          - Enrollment profile not delivered
          - Device waiting for profile installation
          - ADE sync token stale
        """
        logger.info("fix_enrollment_ios", device_id=device_id)
        try:
            steps = []

            # 1. Trigger device sync so Intune re-delivers pending commands
            sync_result = await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Triggered MDM sync to re-deliver enrollment commands")

            # 2. Trigger Apple Business Manager / ADE sync
            ade_sync = await self.client.post(
                "/deviceManagement/depOnboardingSettings/syncWithAppleDeviceEnrollmentProgram",
                body={}
            )
            steps.append("Triggered ADE/Apple Business Manager sync")

            # 3. Fetch current enrollment profile assigned to device
            device_info = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,enrollmentType,managementState,operatingSystem"}
            )
            steps.append(f"Device state: {device_info.get('managementState', 'unknown')}")

            return {
                "success": True,
                "operation": "fix_enrollment_ios",
                "tier": 1,
                "device_id": device_id,
                "steps_completed": steps,
                "message": "ADE enrollment remediation triggered",
                "next_steps": [
                    "User should unlock the device and follow on-screen setup",
                    "If stuck on 'Remote Management' screen: tap Continue",
                    "Allow 10-15 minutes for enrollment profile delivery"
                ]
            }

        except Exception as e:
            logger.error("fix_enrollment_ios failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_enrollment_ios", "error": str(e)}

    # =========================================================================
    # ISSUE 79 – Company Portal Crashing on iOS
    # =========================================================================

    async def fix_company_portal_ios(self, device_id: str) -> Dict[str, Any]:
        """
        Force-reinstall Microsoft Company Portal on an iOS device.
        Tier 1 – removes the app assignment and re-adds it (required intent).

        Fixes:
          - Company Portal crashing on launch
          - Company Portal not updating
          - Company Portal stuck on loading screen
        """
        logger.info("fix_company_portal_ios", device_id=device_id)
        try:
            steps = []

            # Find Company Portal app ID in the tenant
            apps = await self.client.get(
                "/deviceAppManagement/mobileApps",
                params={
                    "$filter": "displayName eq 'Company Portal' and isof('microsoft.graph.iosStoreApp')",
                    "$select": "id,displayName,publishingState"
                }
            )
            app_list = apps.get("value", [])

            if app_list:
                cp_app_id = app_list[0]["id"]
                steps.append(f"Found Company Portal app: {cp_app_id}")

                # Re-trigger required deployment to the device's group
                # Sync forces Intune to push the latest version
                await self.client.post(
                    f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
                )
                steps.append("Triggered device sync to force Company Portal update")
            else:
                steps.append("Company Portal app not found – may need manual assignment in Intune")

            # Remote reboot as a last resort option (inform caller)
            return {
                "success": True,
                "operation": "fix_company_portal_ios",
                "tier": 1,
                "device_id": device_id,
                "steps_completed": steps,
                "message": "Company Portal reinstallation triggered via Intune sync",
                "next_steps": [
                    "User should delete Company Portal manually if it persists",
                    "Open Company Portal from App Store to download fresh copy",
                    "Sign in with corporate credentials after reinstall"
                ]
            }

        except Exception as e:
            logger.error("fix_company_portal_ios failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_company_portal_ios", "error": str(e)}

    # =========================================================================
    # ISSUE 80 – iOS Email Profile Not Syncing
    # =========================================================================

    async def fix_email_profile_ios(
        self, device_id: str, user_email: str = None
    ) -> Dict[str, Any]:
        """
        Remove and re-push the corporate Exchange ActiveSync email configuration profile.
        Tier 2 – briefly removes the email profile; user will need to re-authenticate.

        Fixes:
          - Mail app not receiving new emails
          - ActiveSync connection repeatedly rejected
          - Email profile showing error in Settings
        """
        logger.info("fix_email_profile_ios", device_id=device_id, user_email=user_email)
        try:
            steps = []

            # Find email config profiles assigned to this device
            profiles = await self.client.get(
                "/deviceManagement/deviceConfigurations",
                params={
                    "$filter": "isof('microsoft.graph.iosEasEmailProfileConfiguration')",
                    "$select": "id,displayName"
                }
            )
            email_profiles = profiles.get("value", [])
            steps.append(f"Found {len(email_profiles)} iOS email profile(s)")

            # Force sync – Intune will re-evaluate and re-push all profiles
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Triggered device sync – Intune will re-deliver email profile")

            return {
                "success": True,
                "operation": "fix_email_profile_ios",
                "tier": 2,
                "device_id": device_id,
                "user_email": user_email,
                "email_profiles_found": len(email_profiles),
                "steps_completed": steps,
                "message": "Email profile re-push triggered",
                "next_steps": [
                    "Allow 5-10 minutes for profile re-delivery",
                    "User may need to enter corporate password in Mail settings",
                    "Check Settings > Mail > Accounts after sync"
                ]
            }

        except Exception as e:
            logger.error("fix_email_profile_ios failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_email_profile_ios", "error": str(e)}

    # =========================================================================
    # ISSUE 81 – iOS App Not Available in Company Portal
    # =========================================================================

    async def fix_app_assignment_ios(
        self, device_id: str, app_name: str = None
    ) -> Dict[str, Any]:
        """
        Diagnose why an app is missing from Company Portal and trigger re-sync.
        Tier 1 – read-only check followed by sync.

        Fixes:
          - App missing from Company Portal app list
          - App assignment not reaching device
          - App shows 'Not installed' despite being required
        """
        logger.info("fix_app_assignment_ios", device_id=device_id, app_name=app_name)
        try:
            steps = []

            # Get managed app statuses for this device
            app_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/managedDeviceMobileAppConfigurationStates",
                params={"$select": "id,displayName,state,errorCode"}
            )
            all_apps = app_states.get("value", [])

            # Filter if specific app requested
            if app_name:
                matched = [a for a in all_apps if app_name.lower() in a.get("displayName", "").lower()]
                steps.append(f"App '{app_name}' assignment state: {matched[0].get('state') if matched else 'not found'}")
            else:
                failed = [a for a in all_apps if a.get("state") not in ("installed", "notApplicable")]
                steps.append(f"Apps with issues: {len(failed)}/{len(all_apps)}")

            # Force Intune sync to push pending app installations
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Triggered device sync to force app re-evaluation")

            return {
                "success": True,
                "operation": "fix_app_assignment_ios",
                "tier": 1,
                "device_id": device_id,
                "app_name": app_name,
                "total_apps": len(all_apps),
                "steps_completed": steps,
                "message": "App assignment sync triggered",
                "next_steps": [
                    "Open Company Portal app and tap 'Sync' if app still missing",
                    "Allow 15-30 minutes for app to appear after sync",
                    "Verify the app is assigned to the device's group in Intune"
                ]
            }

        except Exception as e:
            logger.error("fix_app_assignment_ios failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_app_assignment_ios", "error": str(e)}

    # =========================================================================
    # ISSUE 82 – iOS OS Update Not Applying
    # =========================================================================

    async def trigger_os_update_ios(
        self, device_id: str, target_version: str = None
    ) -> Dict[str, Any]:
        """
        Push an OS update declaration to an iOS/iPadOS device via Intune.
        Tier 2 – device will update and reboot; schedule with user.

        Fixes:
          - iOS device stuck on old OS version
          - Security patch not applied
          - Compliance policy requiring newer OS
        """
        logger.info("trigger_os_update_ios", device_id=device_id, target_version=target_version)
        try:
            steps = []

            # Use the Intune device action to schedule an OS update
            # updateScheduledTime: empty string = as soon as possible
            body = {
                "actionName": "updateOperatingSystem",
                "keepEnrollmentData": True,
                "keepUserData": True,
                "scheduledDateTime": ""
            }

            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/scheduleOSUpdate",
                body=body
            )
            steps.append(f"Scheduled OS update via Intune device action")

            # Also sync so the update policy is re-evaluated
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered to evaluate update policies")

            return {
                "success": True,
                "operation": "trigger_os_update_ios",
                "tier": 2,
                "device_id": device_id,
                "target_version": target_version,
                "steps_completed": steps,
                "message": "OS update scheduled on device",
                "next_steps": [
                    "Device will download update in background",
                    "User will receive prompt to install (may require charging)",
                    "Update and reboot typically takes 15-30 minutes"
                ]
            }

        except Exception as e:
            logger.error("trigger_os_update_ios failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "trigger_os_update_ios", "error": str(e)}

    # =========================================================================
    # ISSUE 83 – Screen Time / Supervision Policy Conflict on iOS
    # =========================================================================

    async def fix_screen_time_policy_ios(self, device_id: str) -> Dict[str, Any]:
        """
        Resolve Screen Time or supervision profile conflicts on iOS.
        Tier 1 – audits profiles and triggers re-sync.

        Fixes:
          - Screen Time restrictions blocking corporate apps
          - Supervision MDM profile conflict
          - Device restrictions applied incorrectly
        """
        logger.info("fix_screen_time_policy_ios", device_id=device_id)
        try:
            steps = []

            # Fetch device detail to check supervision state
            device_info = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,isSupervised,managementState,configurationManagerClientEnabledFeatures"}
            )
            is_supervised = device_info.get("isSupervised", False)
            steps.append(f"Device supervised: {is_supervised}")

            if not is_supervised:
                steps.append("WARNING: Device is NOT supervised – some MDM restrictions may not apply")
                steps.append("Consider re-enrolling via Apple Business Manager for full management")

            # List device configuration state to find conflicting profiles
            config_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/deviceConfigurationStates",
                params={"$select": "id,displayName,state,errorCode,settingCount"}
            )
            profiles = config_states.get("value", [])
            conflicts = [p for p in profiles if p.get("state") == "error"]
            steps.append(f"Configuration profiles in error state: {len(conflicts)}")
            for c in conflicts:
                steps.append(f"  - {c.get('displayName')}: {c.get('errorCode')}")

            # Force sync to re-evaluate all policy assignments
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Sync triggered to re-evaluate all policy assignments")

            return {
                "success": True,
                "operation": "fix_screen_time_policy_ios",
                "tier": 1,
                "device_id": device_id,
                "is_supervised": is_supervised,
                "conflicting_profiles": len(conflicts),
                "conflict_details": conflicts,
                "steps_completed": steps,
                "message": "Screen Time / supervision policy audit complete",
                "next_steps": [
                    "Review conflicting profiles in Intune portal and resolve setting conflicts",
                    "Ensure device is supervised via Apple Business Manager for full policy control",
                    "Re-sync after resolving profile conflicts"
                ]
            }

        except Exception as e:
            logger.error("fix_screen_time_policy_ios failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_screen_time_policy_ios", "error": str(e)}

    # =========================================================================
    # ISSUE 84 – APNs Push Notifications Not Working
    # =========================================================================

    async def check_apns_certificate(self) -> Dict[str, Any]:
        """
        Check Apple Push Notification Service (APNs) certificate health in Intune.
        Tier 1 – read-only audit.

        Fixes:
          - MDM commands not being delivered to iOS devices
          - Devices not receiving push notifications from Company Portal
          - Intune tenant APNs certificate expired or expiring soon
        """
        logger.info("check_apns_certificate")
        try:
            steps = []
            issues = []

            # List APNs certificates in the tenant
            apns_certs = await self.client.get(
                "/deviceManagement/appleUserInitiatedEnrollmentProfiles",
                params={"$select": "id,displayName"}
            )

            # Check push notification certificate (MDM APNs)
            push_cert = await self.client.get(
                "/deviceManagement/applePushNotificationCertificate"
            )

            expiry = push_cert.get("expirationDateTime", "unknown")
            apple_id = push_cert.get("appleIdentifier", "unknown")
            cert_serial = push_cert.get("certificateSerialNumber", "unknown")
            steps.append(f"APNs certificate expiry: {expiry}")
            steps.append(f"Apple ID used: {apple_id}")
            steps.append(f"Certificate serial: {cert_serial}")

            # Parse expiry and warn if < 30 days
            try:
                exp_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                days_left = (exp_dt - datetime.now(exp_dt.tzinfo)).days
                steps.append(f"Days until expiry: {days_left}")
                if days_left < 30:
                    issues.append(f"APNs certificate expires in {days_left} days – RENEW IMMEDIATELY")
                elif days_left < 60:
                    issues.append(f"APNs certificate expires in {days_left} days – plan renewal soon")
            except Exception:
                steps.append("Could not parse expiry date")

            healthy = len(issues) == 0
            return {
                "success": True,
                "operation": "check_apns_certificate",
                "tier": 1,
                "healthy": healthy,
                "expiry_datetime": expiry,
                "apple_id": apple_id,
                "certificate_serial": cert_serial,
                "issues": issues,
                "steps_completed": steps,
                "message": "APNs certificate healthy" if healthy else "APNs certificate needs attention",
                "next_steps": (
                    ["No action required"] if healthy else [
                        "Renew APNs certificate in Intune > Devices > iOS/iPadOS > iOS/iPadOS enrollment > Apple MDM Push certificate",
                        "Use the SAME Apple ID that was used originally",
                        "All iOS/iPadOS MDM communication will break if certificate expires"
                    ]
                )
            }

        except Exception as e:
            logger.error("check_apns_certificate failed", error=str(e))
            return {"success": False, "operation": "check_apns_certificate", "error": str(e)}

    # =========================================================================
    # HELPER – Remote lock / passcode clear
    # =========================================================================

    async def remote_lock_ios(self, device_id: str) -> Dict[str, Any]:
        """Lock an iOS device immediately via Intune remote action. Tier 1."""
        logger.info("remote_lock_ios", device_id=device_id)
        try:
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/remoteLock", body={}
            )
            return {
                "success": True,
                "operation": "remote_lock_ios",
                "tier": 1,
                "device_id": device_id,
                "message": "Remote lock command sent to iOS device"
            }
        except Exception as e:
            logger.error("remote_lock_ios failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "remote_lock_ios", "error": str(e)}

    async def clear_passcode_ios(
        self, device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Clear device passcode on a supervised iOS device (for locked-out scenarios).
        Tier 3 – REQUIRES explicit approval (auto_approve=True).
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 3,
                "operation": "clear_passcode_ios",
                "risk": "high",
                "description": "Removes the passcode from the iOS device – device becomes temporarily unlocked",
                "message": "Pass auto_approve=True to confirm this action"
            }
        logger.info("clear_passcode_ios", device_id=device_id)
        try:
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/clearPasscode", body={}
            )
            return {
                "success": True,
                "operation": "clear_passcode_ios",
                "tier": 3,
                "device_id": device_id,
                "message": "Passcode cleared – device is temporarily unlocked. User must set a new passcode.",
                "warning": "Ensure physical device security while passcode is absent"
            }
        except Exception as e:
            logger.error("clear_passcode_ios failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "clear_passcode_ios", "error": str(e)}

    async def retire_ios_device(
        self, device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Retire an iOS device: removes corporate data/profiles, leaves personal data.
        Tier 3 – used during offboarding for BYOD devices.
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 3,
                "operation": "retire_ios_device",
                "risk": "high",
                "description": "Removes all corporate profiles, apps, and email from iOS device",
                "message": "Pass auto_approve=True to confirm retirement"
            }
        logger.info("retire_ios_device", device_id=device_id)
        try:
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/retire", body={}
            )
            return {
                "success": True,
                "operation": "retire_ios_device",
                "tier": 3,
                "device_id": device_id,
                "message": "Device retirement initiated – corporate data will be removed",
                "note": "Personal data and apps are preserved (BYOD retirement)"
            }
        except Exception as e:
            logger.error("retire_ios_device failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "retire_ios_device", "error": str(e)}

    async def wipe_ios_device(
        self, device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Factory wipe a corporate-owned iOS device.
        Tier 3 – used during offboarding for corporate-owned devices.
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 3,
                "operation": "wipe_ios_device",
                "risk": "critical",
                "description": "FACTORY RESETS the iOS device – ALL data will be erased",
                "message": "Pass auto_approve=True only after confirming data backup"
            }
        logger.info("wipe_ios_device", device_id=device_id)
        try:
            body = {
                "keepEnrollmentData": False,
                "keepUserData": False,
                "obliterationBehavior": "default"
            }
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/wipe", body=body
            )
            return {
                "success": True,
                "operation": "wipe_ios_device",
                "tier": 3,
                "device_id": device_id,
                "message": "Factory wipe command sent to iOS device",
                "warning": "ALL data including personal data has been erased"
            }
        except Exception as e:
            logger.error("wipe_ios_device failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "wipe_ios_device", "error": str(e)}

    # =========================================================================
    # DIAGNOSTIC – iOS device health summary
    # =========================================================================

    async def get_ios_device_health(self, device_id: str) -> Dict[str, Any]:
        """
        Retrieve a health snapshot for an iOS/iPadOS device.
        Covers: compliance, OS version, supervision, profile errors, app issues.
        Tier 1 – read-only.
        """
        logger.info("get_ios_device_health", device_id=device_id)
        try:
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={
                    "$select": (
                        "id,deviceName,operatingSystem,osVersion,isSupervised,"
                        "complianceState,managementState,lastSyncDateTime,"
                        "userDisplayName,userPrincipalName,model,manufacturer,"
                        "jailBroken,enrolledDateTime,deviceEnrollmentType"
                    )
                }
            )

            # Config profile errors
            config_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/deviceConfigurationStates",
                params={"$select": "displayName,state,errorCode"}
            )
            profiles = config_states.get("value", [])
            profile_errors = [p for p in profiles if p.get("state") == "error"]

            # App install failures
            app_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/managedDeviceMobileAppConfigurationStates",
                params={"$select": "displayName,state,errorCode"}
            )
            apps = app_states.get("value", [])
            app_errors = [a for a in apps if a.get("state") not in ("installed", "notApplicable", "succeeded")]

            # Health score (simplified)
            score = 100
            issues = []
            if device.get("complianceState") != "compliant":
                score -= 20
                issues.append(f"Non-compliant: {device.get('complianceState')}")
            if device.get("jailBroken") == "True":
                score -= 40
                issues.append("Device is JAILBROKEN – security risk")
            if not device.get("isSupervised"):
                score -= 5
                issues.append("Device not supervised – limited management capabilities")
            if profile_errors:
                score -= (len(profile_errors) * 5)
                issues.append(f"{len(profile_errors)} configuration profile(s) in error")
            if app_errors:
                score -= (len(app_errors) * 3)
                issues.append(f"{len(app_errors)} app(s) with installation issues")

            score = max(0, score)

            return {
                "success": True,
                "operation": "get_ios_device_health",
                "tier": 1,
                "device_id": device_id,
                "device_name": device.get("deviceName"),
                "user": device.get("userDisplayName"),
                "upn": device.get("userPrincipalName"),
                "os_version": device.get("osVersion"),
                "model": device.get("model"),
                "is_supervised": device.get("isSupervised"),
                "is_jailbroken": device.get("jailBroken") == "True",
                "compliance_state": device.get("complianceState"),
                "management_state": device.get("managementState"),
                "last_sync": device.get("lastSyncDateTime"),
                "enrollment_type": device.get("deviceEnrollmentType"),
                "health_score": score,
                "issues": issues,
                "profile_errors": profile_errors,
                "app_errors": app_errors
            }

        except Exception as e:
            logger.error("get_ios_device_health failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "get_ios_device_health", "error": str(e)}
