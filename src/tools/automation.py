"""
Automation Tools - Orchestration and Bulk Operations
"""

import structlog
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from core.graph_client import GraphClient

logger = structlog.get_logger()


class AutomationTools:
    """Tools for automation, orchestration, and bulk operations"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.client = GraphClient(authenticator, config)

        # Import other tool modules for orchestration
        from tools.diagnostic import DiagnosticTools
        from tools.windows_remediation import WindowsRemediationTools
        from tools.macos_remediation import MacOSRemediationTools

        self.diagnostic = DiagnosticTools(authenticator, config)
        self.windows = WindowsRemediationTools(authenticator, config)
        self.macos = MacOSRemediationTools(authenticator, config)

    async def auto_heal_device(
        self,
        device_id: str,
        auto_approve_safe_fixes: bool = True,
        issues_to_fix: list = None
    ) -> Dict[str, Any]:
        """
        Master auto-healing orchestration.
        Diagnoses device and applies appropriate fixes automatically.
        """
        logger.info("auto_heal_device", device_id=device_id, auto_approve=auto_approve_safe_fixes)

        try:
            # Step 1: Comprehensive diagnosis
            logger.info("Step 1: Running comprehensive diagnosis...")
            diagnosis = await self.diagnostic.diagnose_comprehensive(device_id)

            if not diagnosis.get("success"):
                return {
                    "success": False,
                    "error": "Diagnosis failed",
                    "details": diagnosis
                }

            initial_health_score = diagnosis["health_score"]
            platform = diagnosis["platform"]
            all_issues = diagnosis["all_issues"]

            logger.info(
                "Diagnosis complete",
                health_score=initial_health_score,
                issues=len(all_issues),
                platform=platform
            )

            # Filter issues to fix
            if issues_to_fix:
                issues = [i for i in all_issues if i.get("category") in issues_to_fix]
            else:
                issues = all_issues

            # Step 2: Categorize issues by tier
            tier1_fixes = [i for i in issues if self._get_fix_tier(i) == 1 and i.get("auto_fixable")]
            tier2_fixes = [i for i in issues if self._get_fix_tier(i) == 2 and i.get("auto_fixable")]
            tier3_fixes = [i for i in issues if self._get_fix_tier(i) == 3 and i.get("auto_fixable")]

            logger.info(
                "Issues categorized",
                tier1=len(tier1_fixes),
                tier2=len(tier2_fixes),
                tier3=len(tier3_fixes)
            )

            fix_results = []

            # Step 3: Apply Tier 1 fixes automatically
            if tier1_fixes:
                logger.info(f"Applying {len(tier1_fixes)} Tier 1 fixes (automatic)...")
                for issue in tier1_fixes:
                    result = await self._apply_fix(device_id, issue, platform, auto_approve=True)
                    fix_results.append(result)

            # Step 4: Apply Tier 2 fixes (with approval if required)
            if tier2_fixes and auto_approve_safe_fixes:
                logger.info(f"Applying {len(tier2_fixes)} Tier 2 fixes (semi-automatic)...")
                for issue in tier2_fixes:
                    result = await self._apply_fix(device_id, issue, platform, auto_approve=True)
                    fix_results.append(result)
            elif tier2_fixes:
                logger.info(f"Skipping {len(tier2_fixes)} Tier 2 fixes (requires approval)")
                fix_results.append({
                    "tier": 2,
                    "skipped": len(tier2_fixes),
                    "reason": "Requires manual approval (set auto_approve_safe_fixes=True)"
                })

            # Step 5: Tier 3 fixes always require explicit approval
            if tier3_fixes:
                logger.info(f"Skipping {len(tier3_fixes)} Tier 3 fixes (requires explicit approval)")
                fix_results.append({
                    "tier": 3,
                    "skipped": len(tier3_fixes),
                    "reason": "High-risk operations require explicit individual approval",
                    "issues": [i.get("description") for i in tier3_fixes]
                })

            # Step 6: Re-diagnose to measure improvement
            logger.info("Re-diagnosing device to measure improvement...")
            final_diagnosis = await self.diagnostic.diagnose_comprehensive(device_id)
            final_health_score = final_diagnosis.get("health_score", initial_health_score)

            # Step 7: Compile results
            successful_fixes = len([r for r in fix_results if r.get("success")])
            failed_fixes = len([r for r in fix_results if not r.get("success") and "skipped" not in r])
            skipped_fixes = sum([r.get("skipped", 0) for r in fix_results if "skipped" in r])

            result = {
                "success": True,
                "device_id": device_id,
                "device_name": diagnosis["device_name"],
                "platform": platform,
                "healing_summary": {
                    "initial_health_score": initial_health_score,
                    "final_health_score": final_health_score,
                    "improvement": final_health_score - initial_health_score,
                    "total_issues_found": len(all_issues),
                    "fixes_applied": successful_fixes,
                    "fixes_failed": failed_fixes,
                    "fixes_skipped": skipped_fixes
                },
                "fix_results": fix_results,
                "remaining_issues": final_diagnosis.get("all_issues", []),
                "recommendations": final_diagnosis.get("recommendations", [])
            }

            logger.info(
                "Auto-healing complete",
                device_name=diagnosis["device_name"],
                initial_score=initial_health_score,
                final_score=final_health_score,
                improvement=final_health_score - initial_health_score
            )

            return result

        except Exception as e:
            logger.error("auto_heal_device failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "device_id": device_id
            }

    async def bulk_heal_devices(
        self,
        device_ids: list,
        fix_types: list = None,
        max_concurrent: int = 5
    ) -> Dict[str, Any]:
        """
        Heal multiple devices simultaneously.
        """
        logger.info("bulk_heal_devices", device_count=len(device_ids), fix_types=fix_types)

        try:
            # Process devices in batches
            results = []
            batches = [device_ids[i:i + max_concurrent] for i in range(0, len(device_ids), max_concurrent)]

            for batch_num, batch in enumerate(batches, 1):
                logger.info(f"Processing batch {batch_num}/{len(batches)} ({len(batch)} devices)...")

                # Process batch concurrently
                tasks = [
                    self.auto_heal_device(device_id, auto_approve_safe_fixes=True, issues_to_fix=fix_types)
                    for device_id in batch
                ]

                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for device_id, result in zip(batch, batch_results):
                    if isinstance(result, Exception):
                        results.append({
                            "device_id": device_id,
                            "success": False,
                            "error": str(result)
                        })
                    else:
                        results.append(result)

            # Compile summary
            successful = len([r for r in results if r.get("success")])
            failed = len([r for r in results if not r.get("success")])

            return {
                "success": True,
                "total_devices": len(device_ids),
                "successful_heals": successful,
                "failed_heals": failed,
                "fix_types": fix_types or "all",
                "results": results
            }

        except Exception as e:
            logger.error("bulk_heal_devices failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def deploy_remediation_script(
        self,
        name: str,
        detection_script: str,
        remediation_script: str,
        platform: str,
        target_devices: list = None,
        target_groups: list = None,
        schedule: str = "manual"
    ) -> Dict[str, Any]:
        """
        Deploy custom proactive remediation script.
        """
        logger.info("deploy_remediation_script", name=name, platform=platform, schedule=schedule)

        try:
            # Create health script
            script = await self.client.create_device_health_script(
                display_name=name,
                detection_script=detection_script,
                remediation_script=remediation_script,
                run_as_account="system"
            )

            script_id = script["id"]

            # TODO: Assign to target devices/groups
            # This would require additional Graph API calls for assignments

            return {
                "success": True,
                "script_id": script_id,
                "script_name": name,
                "platform": platform,
                "schedule": schedule,
                "message": "Remediation script deployed successfully"
            }

        except Exception as e:
            logger.error("deploy_remediation_script failed", name=name, error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def schedule_maintenance(
        self,
        device_id: str,
        maintenance_tasks: list,
        schedule_time: str,
        recurrence: str = "once"
    ) -> Dict[str, Any]:
        """
        Schedule device maintenance tasks.
        """
        logger.info("schedule_maintenance", device_id=device_id, schedule_time=schedule_time)

        # TODO: Implement scheduling logic
        # This would require a background job scheduler

        return {
            "success": True,
            "device_id": device_id,
            "maintenance_tasks": maintenance_tasks,
            "schedule_time": schedule_time,
            "recurrence": recurrence,
            "message": "Maintenance scheduled (scheduling system not yet implemented)"
        }

    async def sync_device(self, device_id: str, wait_for_completion: bool = True) -> Dict[str, Any]:
        """
        Trigger immediate Intune sync for a device.
        """
        logger.info("sync_device", device_id=device_id, wait=wait_for_completion)

        try:
            # Trigger sync
            await self.client.sync_device(device_id)

            # Get current sync time
            device = await self.client.get_device(device_id)
            last_sync = device.get("lastSyncDateTime")

            if wait_for_completion:
                # Wait for sync to complete (poll for updated lastSyncDateTime)
                max_wait = 60  # seconds
                waited = 0
                while waited < max_wait:
                    await asyncio.sleep(5)
                    waited += 5

                    updated_device = await self.client.get_device(device_id)
                    updated_sync = updated_device.get("lastSyncDateTime")

                    if updated_sync != last_sync:
                        logger.info("Device sync completed", device_id=device_id, wait_time=waited)
                        return {
                            "success": True,
                            "device_id": device_id,
                            "last_sync": updated_sync,
                            "sync_duration_seconds": waited,
                            "message": "Device synced successfully"
                        }

                # Timeout
                logger.warning("Device sync timeout", device_id=device_id)
                return {
                    "success": False,
                    "device_id": device_id,
                    "message": "Sync timeout - device may still be syncing"
                }

            return {
                "success": True,
                "device_id": device_id,
                "last_sync": last_sync,
                "message": "Sync triggered (not waiting for completion)"
            }

        except Exception as e:
            logger.error("sync_device failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    # Helper methods

    def _get_fix_tier(self, issue: Dict[str, Any]) -> int:
        """
        Determine the safety tier for a fix operation.

        Tier 1: Automatic (safe operations)
        Tier 2: Semi-automatic (moderate risk)
        Tier 3: Manual approval (high risk)
        """
        fix_tool = issue.get("fix_tool", "")
        category = issue.get("category", "")

        # Tier 1: Safe, automatic fixes
        tier1_tools = [
            "cleanup_disk_space",
            "reset_network_stack",
            "fix_vpn_configuration",
            "reset_smc",
            "reset_nvram",
            "repair_disk_permissions",
            "fix_spotlight_index",
            "reset_network_settings"
        ]

        # Tier 3: High risk, always requires approval
        tier3_tools = [
            "repair_disk_errors",  # CHKDSK requires reboot
            "rebuild_outlook_profile"  # Data loss risk
        ]

        if fix_tool in tier1_tools:
            return 1
        elif fix_tool in tier3_tools:
            return 3
        else:
            return 2  # Default to Tier 2

    async def _apply_fix(
        self,
        device_id: str,
        issue: Dict[str, Any],
        platform: str,
        auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Apply a specific fix based on issue details.
        """
        fix_tool = issue.get("fix_tool")
        if not fix_tool:
            return {
                "success": False,
                "issue": issue.get("description"),
                "error": "No fix tool available for this issue"
            }

        logger.info("Applying fix", device_id=device_id, fix_tool=fix_tool)

        try:
            # Route to appropriate remediation module
            if platform.lower() == "windows":
                tool_method = getattr(self.windows, fix_tool, None)
            elif platform.lower() == "macos":
                tool_method = getattr(self.macos, fix_tool, None)
            else:
                return {
                    "success": False,
                    "issue": issue.get("description"),
                    "error": f"Unsupported platform: {platform}"
                }

            if not tool_method:
                return {
                    "success": False,
                    "issue": issue.get("description"),
                    "error": f"Fix tool not found: {fix_tool}"
                }

            # Execute fix
            result = await tool_method(device_id, auto_approve=auto_approve)

            return {
                "success": result.get("success", False),
                "issue": issue.get("description"),
                "fix_tool": fix_tool,
                "tier": self._get_fix_tier(issue),
                "result": result
            }

        except Exception as e:
            logger.error("Fix application failed", device_id=device_id, fix_tool=fix_tool, error=str(e))
            return {
                "success": False,
                "issue": issue.get("description"),
                "fix_tool": fix_tool,
                "error": str(e)
            }
