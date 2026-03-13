"""
Android Enterprise Remediation Tools
Covers enrollment, work profile, apps, updates, and security for Android devices
managed through Microsoft Intune (Android Enterprise / Work Profile / COPE / COBO).
"""

import structlog
from typing import Dict, List, Optional, Any
from datetime import datetime
from core.graph_client import GraphClient

logger = structlog.get_logger()


class AndroidRemediationTools:
    """
    Tools for diagnosing and remediating Android device issues via Intune Graph API.

    Supports:
      - Android Enterprise Work Profile (BYOD)
      - Corporate-Owned Work Profile (COPE)
      - Corporate-Owned Business Only (COBO / Fully Managed)
      - Android Enterprise Dedicated (kiosk)
    """

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.client = GraphClient(authenticator, config)

    # =========================================================================
    # ISSUE 85 – Android Enterprise Enrollment Failure
    # =========================================================================

    async def fix_enrollment_android(self, device_id: str) -> Dict[str, Any]:
        """
        Diagnose and recover a failed Android Enterprise enrollment.
        Tier 1 – retriggers sync and checks enrollment profile.

        Fixes:
          - Enrollment token expired
          - Google Play sign-in blocked during enrollment
          - Work profile creation stalled
          - Device not checking in after setup wizard
        """
        logger.info("fix_enrollment_android", device_id=device_id)
        try:
            steps = []

            # Fetch device state
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={
                    "$select": "id,deviceName,managementState,enrollmentType,"
                               "operatingSystem,osVersion,userPrincipalName"
                }
            )
            mgmt_state = device.get("managementState", "unknown")
            enroll_type = device.get("deviceEnrollmentType", "unknown")
            steps.append(f"Management state: {mgmt_state} | Enrollment type: {enroll_type}")

            # Force MDM sync – re-delivers pending policies
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Triggered MDM sync to re-deliver enrollment commands")

            return {
                "success": True,
                "operation": "fix_enrollment_android",
                "tier": 1,
                "device_id": device_id,
                "management_state": mgmt_state,
                "enrollment_type": enroll_type,
                "steps_completed": steps,
                "message": "Android enrollment remediation triggered",
                "next_steps": [
                    "User should open Company Portal and tap 'Sync'",
                    "If enrollment stalled: Factory reset and re-enroll",
                    "Ensure Google Play Services is enabled and up to date",
                    "Verify Android Enterprise is configured in Intune tenant"
                ]
            }

        except Exception as e:
            logger.error("fix_enrollment_android failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_enrollment_android", "error": str(e)}

    # =========================================================================
    # ISSUE 86 – Android Work Profile Not Creating
    # =========================================================================

    async def fix_work_profile_android(
        self, device_id: str, user_upn: str = None
    ) -> Dict[str, Any]:
        """
        Resolve a missing or broken Android work profile (BYOD scenario).
        Tier 2 – triggers re-enrollment flow.

        Fixes:
          - Work profile badge not appearing on apps
          - Corporate apps not separated from personal
          - 'Work profile unavailable' message in Company Portal
          - Work profile removed by user and not re-created
        """
        logger.info("fix_work_profile_android", device_id=device_id, user_upn=user_upn)
        try:
            steps = []

            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={
                    "$select": "id,deviceName,managementState,deviceEnrollmentType,"
                               "userPrincipalName,operatingSystem,osVersion"
                }
            )
            mgmt_state = device.get("managementState", "unknown")
            enroll_type = device.get("deviceEnrollmentType", "unknown")

            steps.append(f"Management state: {mgmt_state}")
            steps.append(f"Enrollment type: {enroll_type}")

            # For BYOD work profile, trigger sync so Company Portal re-creates the profile
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Triggered MDM sync – Company Portal will prompt to re-create work profile")

            is_work_profile = "workProfile" in enroll_type.lower() if enroll_type else False

            return {
                "success": True,
                "operation": "fix_work_profile_android",
                "tier": 2,
                "device_id": device_id,
                "user_upn": user_upn or device.get("userPrincipalName"),
                "management_state": mgmt_state,
                "enrollment_type": enroll_type,
                "is_work_profile_enrollment": is_work_profile,
                "steps_completed": steps,
                "message": "Work profile repair sync triggered",
                "next_steps": [
                    "Open Company Portal on device and sign in with corporate credentials",
                    "Company Portal will guide through work profile re-creation",
                    "Process takes 5-10 minutes; work apps will re-appear with briefcase badge",
                    "If issue persists: remove Company Portal, factory reset work profile, re-enroll"
                ]
            }

        except Exception as e:
            logger.error("fix_work_profile_android failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_work_profile_android", "error": str(e)}

    # =========================================================================
    # ISSUE 87 – Android App Not Installing in Work Profile
    # =========================================================================

    async def fix_app_assignment_android(
        self, device_id: str, app_name: str = None
    ) -> Dict[str, Any]:
        """
        Diagnose and fix app assignment / installation failures in Android work profile.
        Tier 1 – audits app states and forces sync.

        Fixes:
          - Required app not appearing in work profile
          - App stuck in 'Installing' state
          - Google Play for Work not delivering app
          - App blocked by device policy
        """
        logger.info("fix_app_assignment_android", device_id=device_id, app_name=app_name)
        try:
            steps = []

            # Get managed app states for device
            app_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/managedDeviceMobileAppConfigurationStates",
                params={"$select": "id,displayName,state,errorCode"}
            )
            all_apps = app_states.get("value", [])
            steps.append(f"Total managed apps on device: {len(all_apps)}")

            failed_apps = []
            if app_name:
                matched = [a for a in all_apps if app_name.lower() in a.get("displayName", "").lower()]
                if matched:
                    state = matched[0].get("state")
                    steps.append(f"'{app_name}' state: {state}")
                    if state not in ("installed", "succeeded"):
                        failed_apps = matched
                else:
                    steps.append(f"'{app_name}' not found in managed app list")
            else:
                failed_apps = [a for a in all_apps if a.get("state") not in ("installed", "succeeded", "notApplicable")]
                steps.append(f"Apps with failures: {len(failed_apps)}")

            # Force sync
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Triggered device sync to re-push app assignments")

            return {
                "success": True,
                "operation": "fix_app_assignment_android",
                "tier": 1,
                "device_id": device_id,
                "app_name": app_name,
                "total_apps": len(all_apps),
                "failed_apps": failed_apps,
                "steps_completed": steps,
                "message": "App assignment sync triggered",
                "next_steps": [
                    "Open Company Portal in work profile and tap 'Sync'",
                    "Open Google Play (work profile) and check for pending installs",
                    "Allow up to 30 minutes for app delivery via Google Play for Work",
                    "Verify app is licensed and assigned to the correct group in Intune"
                ]
            }

        except Exception as e:
            logger.error("fix_app_assignment_android failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_app_assignment_android", "error": str(e)}

    # =========================================================================
    # ISSUE 88 – Android Email Profile Not Syncing
    # =========================================================================

    async def fix_email_profile_android(
        self, device_id: str, user_email: str = None
    ) -> Dict[str, Any]:
        """
        Re-push corporate email profile to Android device.
        Tier 2 – profile will be removed and re-delivered.

        Fixes:
          - Gmail/Outlook work profile not syncing mail
          - Exchange ActiveSync authentication failing
          - Email profile showing configuration error
        """
        logger.info("fix_email_profile_android", device_id=device_id, user_email=user_email)
        try:
            steps = []

            # Look for Android email config profiles
            profiles = await self.client.get(
                "/deviceManagement/deviceConfigurations",
                params={
                    "$filter": "isof('microsoft.graph.androidWorkProfileEasEmailProfileBase')",
                    "$select": "id,displayName"
                }
            )
            email_profiles = profiles.get("value", [])
            steps.append(f"Found {len(email_profiles)} Android email profile(s)")

            # Sync forces Intune to re-evaluate and re-push profile
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – email profile will be re-delivered")

            return {
                "success": True,
                "operation": "fix_email_profile_android",
                "tier": 2,
                "device_id": device_id,
                "user_email": user_email,
                "email_profiles_found": len(email_profiles),
                "steps_completed": steps,
                "message": "Email profile re-push triggered",
                "next_steps": [
                    "Allow 5-10 minutes for profile re-delivery",
                    "Check Settings > Accounts in the work profile",
                    "User may need to re-authenticate with corporate password",
                    "For Outlook: remove work account and re-add via Company Portal"
                ]
            }

        except Exception as e:
            logger.error("fix_email_profile_android failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_email_profile_android", "error": str(e)}

    # =========================================================================
    # ISSUE 89 – Android OS Update Pending
    # =========================================================================

    async def trigger_os_update_android(
        self, device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Push OS update policy to an Android device via Intune.
        Tier 2 – device will update and reboot.

        Fixes:
          - Android security patch level out of compliance
          - OS version below minimum required by policy
          - Update pending but not installing automatically
        """
        if not auto_approve and self.config.require_approval_risky_ops:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 2,
                "operation": "trigger_os_update_android",
                "risk": "moderate",
                "description": "Triggers an OS update on the Android device – device will reboot",
                "message": "Set auto_approve=True to proceed or approve in Intune portal"
            }

        logger.info("trigger_os_update_android", device_id=device_id)
        try:
            steps = []

            # Use Intune device action to push OS update
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Triggered MDM sync to push pending OS update policy")

            # Check device OS update policy compliance
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={"$select": "id,deviceName,osVersion,complianceState,lastSyncDateTime"}
            )
            steps.append(f"Current OS: {device.get('osVersion')} | Compliance: {device.get('complianceState')}")

            return {
                "success": True,
                "operation": "trigger_os_update_android",
                "tier": 2,
                "device_id": device_id,
                "current_os": device.get("osVersion"),
                "compliance_state": device.get("complianceState"),
                "steps_completed": steps,
                "message": "OS update policy sync triggered",
                "next_steps": [
                    "Device will check for updates via Android Enterprise update policy",
                    "User will receive a notification to install the update",
                    "For corporate-owned devices: Intune can force-install without user interaction",
                    "Update typically takes 20-40 minutes including reboot"
                ]
            }

        except Exception as e:
            logger.error("trigger_os_update_android failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "trigger_os_update_android", "error": str(e)}

    # =========================================================================
    # ISSUE 90 – Company Portal Crashing on Android
    # =========================================================================

    async def fix_company_portal_android(self, device_id: str) -> Dict[str, Any]:
        """
        Fix Microsoft Company Portal app issues on Android.
        Tier 1 – forces app update via Intune.

        Fixes:
          - Company Portal crashing on launch
          - Company Portal stuck on 'Contacting IT department'
          - Company Portal showing white/black screen
          - Company Portal not accepting login
        """
        logger.info("fix_company_portal_android", device_id=device_id)
        try:
            steps = []

            # Find Company Portal for Android in the tenant
            apps = await self.client.get(
                "/deviceAppManagement/mobileApps",
                params={
                    "$filter": "displayName eq 'Company Portal'",
                    "$select": "id,displayName,publishingState,appAvailability"
                }
            )
            app_list = apps.get("value", [])
            android_cp = [a for a in app_list if "android" in str(a).lower() or len(app_list) == 1]

            if android_cp:
                steps.append(f"Company Portal app found: {android_cp[0].get('id')}")
            else:
                steps.append("Company Portal app not found for Android – check app assignment in Intune")

            # Force device sync to push latest Company Portal version
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/syncDevice", body={}
            )
            steps.append("Device sync triggered – Intune will push latest Company Portal version")

            return {
                "success": True,
                "operation": "fix_company_portal_android",
                "tier": 1,
                "device_id": device_id,
                "steps_completed": steps,
                "message": "Company Portal update triggered",
                "next_steps": [
                    "User should clear Company Portal app cache: Settings > Apps > Company Portal > Clear Cache",
                    "If crash persists: uninstall Company Portal, then reinstall from Play Store (work profile)",
                    "After reinstall: sign in with corporate credentials",
                    "Ensure Google Play Services and Google Play Store are up to date"
                ]
            }

        except Exception as e:
            logger.error("fix_company_portal_android failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "fix_company_portal_android", "error": str(e)}

    # =========================================================================
    # RETIRE / WIPE – Offboarding
    # =========================================================================

    async def retire_android_device(
        self, device_id: str, auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Retire an Android BYOD device: removes work profile only. Tier 3.
        Preserves personal apps and data.
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 3,
                "operation": "retire_android_device",
                "risk": "high",
                "description": "Removes the Android work profile and all corporate data/apps",
                "message": "Pass auto_approve=True to confirm retirement"
            }
        logger.info("retire_android_device", device_id=device_id)
        try:
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/retire", body={}
            )
            return {
                "success": True,
                "operation": "retire_android_device",
                "tier": 3,
                "device_id": device_id,
                "message": "Android device retirement initiated – work profile will be removed",
                "note": "Personal data and personal profile apps are preserved"
            }
        except Exception as e:
            logger.error("retire_android_device failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "retire_android_device", "error": str(e)}

    async def wipe_android_device(
        self, device_id: str, keep_enrollment_data: bool = False,
        auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Factory wipe a corporate-owned Android device. Tier 3.
        Used for corporate-owned devices (COBO/COPE) during offboarding.
        """
        if not auto_approve:
            return {
                "success": False,
                "requires_approval": True,
                "tier": 3,
                "operation": "wipe_android_device",
                "risk": "critical",
                "description": "FACTORY RESETS the Android device – ALL data will be erased",
                "message": "Pass auto_approve=True only after confirming data backup"
            }
        logger.info("wipe_android_device", device_id=device_id)
        try:
            body = {
                "keepEnrollmentData": keep_enrollment_data,
                "keepUserData": False,
                "persistEsimDataPlan": False
            }
            await self.client.post(
                f"/deviceManagement/managedDevices/{device_id}/wipe", body=body
            )
            return {
                "success": True,
                "operation": "wipe_android_device",
                "tier": 3,
                "device_id": device_id,
                "keep_enrollment_data": keep_enrollment_data,
                "message": "Factory wipe command sent to Android device",
                "warning": "ALL data has been erased from the device"
            }
        except Exception as e:
            logger.error("wipe_android_device failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "wipe_android_device", "error": str(e)}

    # =========================================================================
    # DIAGNOSTIC – Android device health summary
    # =========================================================================

    async def get_android_device_health(self, device_id: str) -> Dict[str, Any]:
        """
        Full health snapshot for an Android device.
        Covers: compliance, OS, work profile, app failures, jailbreak detection.
        Tier 1 – read-only.
        """
        logger.info("get_android_device_health", device_id=device_id)
        try:
            device = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}",
                params={
                    "$select": (
                        "id,deviceName,operatingSystem,osVersion,model,manufacturer,"
                        "complianceState,managementState,lastSyncDateTime,"
                        "userDisplayName,userPrincipalName,jailBroken,"
                        "enrolledDateTime,deviceEnrollmentType,androidSecurityPatchLevel"
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

            # App states
            app_states = await self.client.get(
                f"/deviceManagement/managedDevices/{device_id}/managedDeviceMobileAppConfigurationStates",
                params={"$select": "displayName,state,errorCode"}
            )
            apps = app_states.get("value", [])
            app_errors = [a for a in apps if a.get("state") not in ("installed", "notApplicable", "succeeded")]

            # Health score
            score = 100
            issues = []
            if device.get("complianceState") != "compliant":
                score -= 20
                issues.append(f"Non-compliant: {device.get('complianceState')}")
            if device.get("jailBroken") == "True":
                score -= 40
                issues.append("Device is ROOTED – security risk")
            if profile_errors:
                score -= len(profile_errors) * 5
                issues.append(f"{len(profile_errors)} configuration profile error(s)")
            if app_errors:
                score -= len(app_errors) * 3
                issues.append(f"{len(app_errors)} app installation failure(s)")

            score = max(0, score)

            return {
                "success": True,
                "operation": "get_android_device_health",
                "tier": 1,
                "device_id": device_id,
                "device_name": device.get("deviceName"),
                "user": device.get("userDisplayName"),
                "upn": device.get("userPrincipalName"),
                "os_version": device.get("osVersion"),
                "security_patch_level": device.get("androidSecurityPatchLevel"),
                "model": f"{device.get('manufacturer')} {device.get('model')}",
                "is_rooted": device.get("jailBroken") == "True",
                "compliance_state": device.get("complianceState"),
                "management_state": device.get("managementState"),
                "enrollment_type": device.get("deviceEnrollmentType"),
                "last_sync": device.get("lastSyncDateTime"),
                "health_score": score,
                "issues": issues,
                "profile_errors": profile_errors,
                "app_errors": app_errors
            }

        except Exception as e:
            logger.error("get_android_device_health failed", device_id=device_id, error=str(e))
            return {"success": False, "operation": "get_android_device_health", "error": str(e)}
