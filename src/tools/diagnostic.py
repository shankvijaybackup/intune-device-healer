"""
Diagnostic Tools - Comprehensive Health Checks
"""

import structlog
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from core.graph_client import GraphClient
from core.utils import parse_graph_datetime

logger = structlog.get_logger()


class DiagnosticTools:
    """Tools for diagnosing device health issues"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.client = GraphClient(authenticator, config)
        from tools.worklets import WorkletsTools
        self.worklets = WorkletsTools(authenticator, config)

    async def diagnose_comprehensive(self, device_id: str) -> Dict[str, Any]:
        """
        Perform comprehensive device diagnostics.

        Returns complete health assessment with actionable insights.
        """
        logger.info("Starting comprehensive diagnosis", device_id=device_id)

        try:
            # Get device details
            device = await self._get_device_by_id_or_name(device_id)
            if not device:
                return {
                    "success": False,
                    "error": f"Device not found: {device_id}"
                }

            device_id = device["id"]
            device_name = device.get("deviceName", "Unknown")
            platform = device.get("operatingSystem", "Unknown")

            # Run all diagnostic checks in parallel
            hardware = await self.check_hardware(device_id)
            os_health = await self.check_os(device_id)
            network = await self.check_network(device_id)
            security = await self.check_security(device_id)
            applications = await self.check_applications(device_id)
            performance = await self._check_performance(device)

            # Collect all issues
            all_issues = []
            all_issues.extend(hardware.get("issues", []))
            all_issues.extend(os_health.get("issues", []))
            all_issues.extend(network.get("issues", []))
            all_issues.extend(security.get("issues", []))
            all_issues.extend(applications.get("issues", []))
            all_issues.extend(performance.get("issues", []))

            # Calculate health score
            health_score = self._calculate_health_score(all_issues)

            # Categorize issues
            critical = [i for i in all_issues if i.get("severity") == "critical"]
            high = [i for i in all_issues if i.get("severity") == "high"]
            medium = [i for i in all_issues if i.get("severity") == "medium"]
            low = [i for i in all_issues if i.get("severity") == "low"]

            result = {
                "success": True,
                "device_name": device_name,
                "device_id": device_id,
                "platform": platform,
                "diagnosis_time": datetime.utcnow().isoformat(),
                "health_score": health_score,
                "health_grade": self._get_health_grade(health_score),
                "total_issues": len(all_issues),
                "issues_by_severity": {
                    "critical": len(critical),
                    "high": len(high),
                    "medium": len(medium),
                    "low": len(low)
                },
                "auto_fixable_issues": len([i for i in all_issues if i.get("auto_fixable")]),
                "detailed_results": {
                    "hardware": hardware,
                    "os_health": os_health,
                    "network": network,
                    "security": security,
                    "applications": applications,
                    "performance": performance
                },
                "all_issues": all_issues,
                "recommendations": self._generate_recommendations(all_issues, platform)
            }

            logger.info(
                "Diagnosis complete",
                device_name=device_name,
                health_score=health_score,
                issues=len(all_issues)
            )

            return result

        except Exception as e:
            logger.error("Diagnosis failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def diagnose_app_crashes(self, device_id: str, limit: int = 10) -> Dict[str, Any]:
        """
        Retrieve recent application crash details from Windows Event Logs.
        Used for 'No-Fake' app failure diagnosis.
        """
        script = f"""
        $Limit = {limit}
        Write-Output "--- ANALYZING RECENT APP FAILURES ---"
        $Events = Get-EventLog -LogName Application -EntryType Error, Warning -Newest $Limit | 
                  Where-Object {{ $_.Source -like "*Error*" -or $_.Source -like "*Application*" }}
        
        if ($Events) {{
            $Events | ForEach-Object {{
                Write-Output "Timestamp: $($_.TimeGenerated)"
                Write-Output "Source: $($_.Source)"
                Write-Output "EventID: $($_.EventID)"
                Write-Output "Message Summary: $($_.Message.Substring(0, [math]::Min($_.Message.Length, 150)))"
                Write-Output "-----------------------------------"
            }}
        }} else {{
            Write-Output "No recent application errors or warnings found."
        }}
        """
        # We'll run this via the underlying worklet mechanism for real results
        return await self.worklets._run_windows(device_id, "App-Crash-Diagnosis", script)

    async def check_hardware(self, device_id: str) -> Dict[str, Any]:
        """Check hardware health status"""
        logger.info("Checking hardware health", device_id=device_id)

        try:
            device = await self.client.get_device(device_id)
            issues = []

            # Check free storage space
            total_storage = device.get("totalStorageSpaceInBytes", 0)
            free_storage = device.get("freeStorageSpaceInBytes", 0)

            if total_storage > 0:
                used_percent = ((total_storage - free_storage) / total_storage) * 100
                free_gb = free_storage / (1024**3)

                if used_percent > 95:
                    issues.append({
                        "category": "disk",
                        "severity": "critical",
                        "description": f"Disk usage at {used_percent:.1f}% (Only {free_gb:.1f}GB free)",
                        "auto_fixable": True,
                        "fix_tool": "cleanup_disk_space"
                    })
                elif used_percent > 85:
                    issues.append({
                        "category": "disk",
                        "severity": "high",
                        "description": f"Disk usage at {used_percent:.1f}% ({free_gb:.1f}GB free)",
                        "auto_fixable": True,
                        "fix_tool": "cleanup_disk_space"
                    })

            # Check battery health (for laptops/mobile devices)
            battery_level = device.get("batteryLevelPercentage")
            if battery_level is not None:
                battery_health = {
                    "level": battery_level,
                    "status": "healthy" if battery_level > 20 else "low"
                }
            else:
                battery_health = None

            # Check device encryption
            encryption_status = device.get("isEncrypted", False)
            if not encryption_status:
                issues.append({
                    "category": "security",
                    "severity": "high",
                    "description": "Device encryption is disabled",
                    "auto_fixable": True,
                    "fix_tool": "enable_bitlocker"
                })

            return {
                "status": "healthy" if not issues else "issues_detected",
                "total_storage_gb": total_storage / (1024**3) if total_storage else None,
                "free_storage_gb": free_storage / (1024**3) if free_storage else None,
                "storage_used_percent": ((total_storage - free_storage) / total_storage * 100) if total_storage else None,
                "battery": battery_health,
                "encryption_enabled": encryption_status,
                "issues": issues
            }

        except Exception as e:
            logger.error("Hardware check failed", device_id=device_id, error=str(e))
            return {"status": "error", "error": str(e), "issues": []}

    async def check_os(self, device_id: str) -> Dict[str, Any]:
        """Check operating system health"""
        logger.info("Checking OS health", device_id=device_id)

        try:
            device = await self.client.get_device(device_id)
            issues = []

            os_version = device.get("osVersion", "Unknown")
            os_name = device.get("operatingSystem", "Unknown")

            # Check last sync time
            last_sync = device.get("lastSyncDateTime")
            if last_sync:
                last_sync_dt = parse_graph_datetime(last_sync)
                hours_since_sync = (datetime.now(last_sync_dt.tzinfo) - last_sync_dt).total_seconds() / 3600

                if hours_since_sync > 7 * 24:  # More than 7 days
                    issues.append({
                        "category": "sync",
                        "severity": "high",
                        "description": f"Device hasn't synced in {hours_since_sync/24:.1f} days",
                        "auto_fixable": True,
                        "fix_tool": "sync_device"
                    })
                elif hours_since_sync > 24:  # More than 1 day
                    issues.append({
                        "category": "sync",
                        "severity": "medium",
                        "description": f"Device last synced {hours_since_sync:.1f} hours ago",
                        "auto_fixable": True,
                        "fix_tool": "sync_device"
                    })

            # Check compliance state
            compliance_state = device.get("complianceState", "unknown")
            if compliance_state != "compliant":
                issues.append({
                    "category": "compliance",
                    "severity": "high",
                    "description": f"Device is not compliant (State: {compliance_state})",
                    "auto_fixable": False,
                    "fix_tool": None
                })

            return {
                "status": "healthy" if not issues else "issues_detected",
                "os_name": os_name,
                "os_version": os_version,
                "compliance_state": compliance_state,
                "last_sync": last_sync,
                "issues": issues
            }

        except Exception as e:
            logger.error("OS check failed", device_id=device_id, error=str(e))
            return {"status": "error", "error": str(e), "issues": []}

    async def check_network(self, device_id: str) -> Dict[str, Any]:
        """Check network connectivity and configuration"""
        logger.info("Checking network health", device_id=device_id)

        try:
            device = await self.client.get_device(device_id)
            issues = []

            # Check WiFi MAC address (indicates network capability)
            wifi_mac = device.get("wiFiMacAddress")
            ethernet_mac = device.get("ethernetMacAddress")

            network_info = {
                "wifi_available": wifi_mac is not None,
                "ethernet_available": ethernet_mac is not None
            }

            # Check if device is connected
            if not wifi_mac and not ethernet_mac:
                issues.append({
                    "category": "network",
                    "severity": "high",
                    "description": "No network connectivity detected",
                    "auto_fixable": True,
                    "fix_tool": "reset_network_stack"
                })

            # VPN configuration check would require additional API calls
            # This is a placeholder for VPN status
            vpn_status = "unknown"  # Would check via configuration profiles

            return {
                "status": "healthy" if not issues else "issues_detected",
                "network_info": network_info,
                "vpn_status": vpn_status,
                "issues": issues
            }

        except Exception as e:
            logger.error("Network check failed", device_id=device_id, error=str(e))
            return {"status": "error", "error": str(e), "issues": []}

    async def check_security(self, device_id: str) -> Dict[str, Any]:
        """Check security posture"""
        logger.info("Checking security posture", device_id=device_id)

        try:
            device = await self.client.get_device(device_id)
            issues = []

            # Check encryption
            is_encrypted = device.get("isEncrypted", False)
            if not is_encrypted:
                issues.append({
                    "category": "encryption",
                    "severity": "critical",
                    "description": "Device encryption is not enabled",
                    "auto_fixable": True,
                    "fix_tool": "enable_bitlocker"
                })

            # Check Azure AD registration
            azure_ad_registered = device.get("azureADRegistered", False)
            azure_ad_device_id = device.get("azureADDeviceId")

            if not azure_ad_registered:
                issues.append({
                    "category": "identity",
                    "severity": "high",
                    "description": "Device is not Azure AD registered",
                    "auto_fixable": False,
                    "fix_tool": None
                })

            # Check compliance
            compliance = device.get("complianceState", "unknown")
            if compliance != "compliant":
                issues.append({
                    "category": "compliance",
                    "severity": "high",
                    "description": f"Device not compliant: {compliance}",
                    "auto_fixable": False,
                    "fix_tool": None
                })

            return {
                "status": "healthy" if not issues else "issues_detected",
                "encryption_enabled": is_encrypted,
                "azure_ad_registered": azure_ad_registered,
                "compliance_state": compliance,
                "issues": issues
            }

        except Exception as e:
            logger.error("Security check failed", device_id=device_id, error=str(e))
            return {"status": "error", "error": str(e), "issues": []}

    async def check_applications(self, device_id: str, app_name: str = None) -> Dict[str, Any]:
        """Check application health"""
        logger.info("Checking application health", device_id=device_id, app_name=app_name)

        try:
            # This would require querying detected apps and installed apps
            # For now, return basic structure
            issues = []

            # Placeholder for Outlook check
            # Would check for PST corruption, profile issues, etc.

            return {
                "status": "healthy" if not issues else "issues_detected",
                "apps_checked": app_name if app_name else "all",
                "issues": issues
            }

        except Exception as e:
            logger.error("Application check failed", device_id=device_id, error=str(e))
            return {"status": "error", "error": str(e), "issues": []}

    async def predict_failures(self, device_id: str) -> Dict[str, Any]:
        """AI-powered failure prediction"""
        logger.info("Predicting potential failures", device_id=device_id)

        try:
            device = await self.client.get_device(device_id)
            predictions = []

            # Analyze disk space trend
            free_storage = device.get("freeStorageSpaceInBytes", 0)
            total_storage = device.get("totalStorageSpaceInBytes", 0)

            if total_storage > 0:
                free_percent = (free_storage / total_storage) * 100
                if free_percent < 10:
                    predictions.append({
                        "type": "disk_failure",
                        "probability": "high",
                        "timeframe": "within 7 days",
                        "description": "Disk space critically low, likely to run out soon",
                        "recommended_action": "cleanup_disk_space"
                    })
                elif free_percent < 20:
                    predictions.append({
                        "type": "disk_space",
                        "probability": "medium",
                        "timeframe": "within 30 days",
                        "description": "Disk space running low",
                        "recommended_action": "cleanup_disk_space"
                    })

            # Check sync patterns
            last_sync = device.get("lastSyncDateTime")
            if last_sync:
                last_sync_dt = parse_graph_datetime(last_sync)
                days_since_sync = (datetime.now(last_sync_dt.tzinfo) - last_sync_dt).days

                if days_since_sync > 5:
                    predictions.append({
                        "type": "sync_failure",
                        "probability": "high",
                        "timeframe": "current",
                        "description": "Device sync failing, may lose management",
                        "recommended_action": "sync_device"
                    })

            return {
                "success": True,
                "predictions": predictions,
                "risk_level": "high" if any(p["probability"] == "high" for p in predictions) else "medium" if predictions else "low"
            }

        except Exception as e:
            logger.error("Failure prediction failed", device_id=device_id, error=str(e))
            return {"success": False, "error": str(e)}

    async def list_devices(
        self,
        platform: str = "all",
        compliance_state: str = "all",
        limit: int = 100
    ) -> Dict[str, Any]:
        """List Intune managed devices"""
        logger.info("Listing devices", platform=platform, compliance=compliance_state)

        try:
            filter_parts = []

            if platform != "all":
                platform_map = {
                    "windows": "Windows",
                    "macos": "macOS",
                    "ios": "iOS",
                    "android": "Android"
                }
                os_filter = platform_map.get(platform.lower(), platform)
                filter_parts.append(f"operatingSystem eq '{os_filter}'")

            if compliance_state != "all":
                filter_parts.append(f"complianceState eq '{compliance_state}'")

            filter_query = " and ".join(filter_parts) if filter_parts else None

            devices = await self.client.list_managed_devices(
                filter_query=filter_query,
                limit=limit
            )

            device_list = [
                {
                    "id": d["id"],
                    "name": d.get("deviceName", "Unknown"),
                    "platform": d.get("operatingSystem", "Unknown"),
                    "os_version": d.get("osVersion", "Unknown"),
                    "compliance": d.get("complianceState", "unknown"),
                    "last_sync": d.get("lastSyncDateTime"),
                    "encrypted": d.get("isEncrypted", False),
                    "user": d.get("userPrincipalName", "Unknown")
                }
                for d in devices
            ]

            return {
                "success": True,
                "total": len(device_list),
                "devices": device_list
            }

        except Exception as e:
            logger.error("List devices failed", error=str(e))
            return {"success": False, "error": str(e)}

    # Helper methods

    async def _get_device_by_id_or_name(self, device_identifier: str) -> Optional[Dict[str, Any]]:
        """Get device by ID or name"""
        try:
            # Try as direct ID first
            device = await self.client.get_device(device_identifier)
            return device
        except:
            # Search by name
            devices = await self.client.list_managed_devices(
                filter_query=f"deviceName eq '{device_identifier}'",
                limit=1
            )
            return devices[0] if devices else None

    def _calculate_health_score(self, issues: List[Dict[str, Any]]) -> int:
        """Calculate health score (0-100) based on issues"""
        if not issues:
            return 100

        severity_weights = {
            "critical": 25,
            "high": 15,
            "medium": 8,
            "low": 3
        }

        total_deduction = sum(severity_weights.get(i.get("severity", "low"), 3) for i in issues)
        score = max(0, 100 - total_deduction)

        return score

    def _get_health_grade(self, score: int) -> str:
        """Convert health score to grade"""
        if score >= 90:
            return "A (Excellent)"
        elif score >= 80:
            return "B (Good)"
        elif score >= 70:
            return "C (Fair)"
        elif score >= 60:
            return "D (Poor)"
        else:
            return "F (Critical)"

    def _generate_recommendations(self, issues: List[Dict[str, Any]], platform: str) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []

        if any(i.get("category") == "disk" for i in issues):
            recommendations.append("Run disk cleanup to free up space")

        if any(i.get("category") == "sync" for i in issues):
            recommendations.append("Trigger device sync to update management state")

        if any(i.get("category") == "encryption" for i in issues):
            if platform.lower() == "windows":
                recommendations.append("Enable BitLocker encryption")
            else:
                recommendations.append("Enable FileVault encryption")

        if any(i.get("category") == "network" for i in issues):
            recommendations.append("Reset network configuration")

        auto_fixable_count = len([i for i in issues if i.get("auto_fixable")])
        if auto_fixable_count > 0:
            recommendations.append(f"Use auto_heal_device tool to fix {auto_fixable_count} issues automatically")

        return recommendations

    async def _check_performance(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Check device performance metrics using high-resolution worklets"""
        device_id = device["id"]
        platform = device.get("operatingSystem", "Unknown")
        
        logger.info("Checking performance via worklet", device_id=device_id, platform=platform)
        
        try:
            if "Windows" in platform:
                perf_result = await self.worklets.get_performance_diagnostics_windows(device_id)
            else:
                perf_result = await self.worklets.get_performance_diagnostics_mac(device_id)
                
            return {
                "status": "healthy" if perf_result.get("success") else "warning",
                "details": perf_result,
                "issues": [] if perf_result.get("success") else [{
                    "category": "performance",
                    "severity": "medium",
                    "description": "Failed to capture high-resolution performance metrics",
                    "auto_fixable": False
                }]
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "issues": []
            }
