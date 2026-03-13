"""
Monitoring Tools - Fleet Health, Reporting, and Analytics
"""

import structlog
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
from core.graph_client import GraphClient
from core.utils import parse_graph_datetime

logger = structlog.get_logger()


class MonitoringTools:
    """Tools for monitoring, reporting, and analytics"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.client = GraphClient(authenticator, config)

        # Import diagnostic tools for health checks
        from tools.diagnostic import DiagnosticTools
        self.diagnostic = DiagnosticTools(authenticator, config)

    async def get_fleet_health_dashboard(self) -> Dict[str, Any]:
        """
        Get real-time health dashboard for entire device fleet.
        """
        logger.info("get_fleet_health_dashboard")

        try:
            # Get all managed devices
            devices = await self.client.list_managed_devices(limit=1000)

            total_devices = len(devices)
            if total_devices == 0:
                return {
                    "success": True,
                    "total_devices": 0,
                    "message": "No devices found in Intune"
                }

            # Analyze fleet health
            by_platform = defaultdict(int)
            by_compliance = defaultdict(int)
            by_encryption = {"encrypted": 0, "not_encrypted": 0}
            sync_issues = []
            low_storage = []
            noncompliant_devices = []

            for device in devices:
                # Platform distribution
                platform = device.get("operatingSystem", "Unknown")
                by_platform[platform] += 1

                # Compliance state
                compliance = device.get("complianceState", "unknown")
                by_compliance[compliance] += 1

                if compliance != "compliant":
                    noncompliant_devices.append({
                        "id": device["id"],
                        "name": device.get("deviceName", "Unknown"),
                        "compliance_state": compliance
                    })

                # Encryption status
                if device.get("isEncrypted", False):
                    by_encryption["encrypted"] += 1
                else:
                    by_encryption["not_encrypted"] += 1

                # Sync issues (haven't synced in 7+ days)
                last_sync = device.get("lastSyncDateTime")
                if last_sync:
                    last_sync_dt = parse_graph_datetime(last_sync)
                    days_since_sync = (datetime.now(last_sync_dt.tzinfo) - last_sync_dt).days
                    if days_since_sync > 7:
                        sync_issues.append({
                            "id": device["id"],
                            "name": device.get("deviceName", "Unknown"),
                            "days_since_sync": days_since_sync
                        })

                # Low storage (less than 10% free)
                total_storage = device.get("totalStorageSpaceInBytes", 0)
                free_storage = device.get("freeStorageSpaceInBytes", 0)
                if total_storage > 0:
                    free_percent = (free_storage / total_storage) * 100
                    if free_percent < 10:
                        low_storage.append({
                            "id": device["id"],
                            "name": device.get("deviceName", "Unknown"),
                            "free_percent": round(free_percent, 1),
                            "free_gb": round(free_storage / (1024**3), 2)
                        })

            # Calculate health categories
            healthy = by_compliance.get("compliant", 0)
            warning = total_devices - healthy - by_compliance.get("noncompliant", 0)
            critical = by_compliance.get("noncompliant", 0)

            # Top issues analysis
            top_issues = []
            if low_storage:
                top_issues.append({
                    "issue": "Low disk space",
                    "count": len(low_storage),
                    "severity": "high",
                    "devices": low_storage[:5]  # Top 5
                })
            if sync_issues:
                top_issues.append({
                    "issue": "Sync issues (7+ days)",
                    "count": len(sync_issues),
                    "severity": "high",
                    "devices": sync_issues[:5]
                })
            if by_encryption["not_encrypted"] > 0:
                top_issues.append({
                    "issue": "Encryption not enabled",
                    "count": by_encryption["not_encrypted"],
                    "severity": "critical"
                })
            if noncompliant_devices:
                top_issues.append({
                    "issue": "Non-compliant devices",
                    "count": len(noncompliant_devices),
                    "severity": "high",
                    "devices": noncompliant_devices[:5]
                })

            # Sort top issues by severity and count
            top_issues.sort(key=lambda x: (
                {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(x["severity"], 0),
                x["count"]
            ), reverse=True)

            result = {
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "fleet_summary": {
                    "total_devices": total_devices,
                    "healthy": healthy,
                    "warning": warning,
                    "critical": critical,
                    "healthy_percent": round((healthy / total_devices) * 100, 1),
                    "avg_health_score": round((healthy / total_devices) * 100, 0)  # Simplified
                },
                "by_platform": dict(by_platform),
                "by_compliance": dict(by_compliance),
                "security": {
                    "encrypted": by_encryption["encrypted"],
                    "not_encrypted": by_encryption["not_encrypted"],
                    "encryption_rate": round((by_encryption["encrypted"] / total_devices) * 100, 1)
                },
                "top_issues": top_issues[:10],  # Top 10 issues
                "devices_needing_attention": len(sync_issues) + len(low_storage) + len(noncompliant_devices)
            }

            logger.info(
                "Fleet health dashboard generated",
                total_devices=total_devices,
                healthy=healthy,
                issues=len(top_issues)
            )

            return result

        except Exception as e:
            logger.error("get_fleet_health_dashboard failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def get_device_health_score(self, device_id: str) -> Dict[str, Any]:
        """
        Calculate comprehensive health score (0-100) for a device.
        """
        logger.info("get_device_health_score", device_id=device_id)

        try:
            # Run comprehensive diagnosis
            diagnosis = await self.diagnostic.diagnose_comprehensive(device_id)

            if not diagnosis.get("success"):
                return {
                    "success": False,
                    "error": "Could not calculate health score",
                    "details": diagnosis
                }

            # Extract health score breakdown
            health_score = diagnosis["health_score"]
            health_grade = diagnosis["health_grade"]

            # Category scores
            category_scores = {}

            detailed_results = diagnosis.get("detailed_results", {})

            # Calculate category-specific scores
            for category, results in detailed_results.items():
                issues = results.get("issues", [])
                if not issues:
                    category_scores[category] = 100
                else:
                    severity_weights = {"critical": 30, "high": 20, "medium": 10, "low": 5}
                    deduction = sum(severity_weights.get(i.get("severity", "low"), 5) for i in issues)
                    category_scores[category] = max(0, 100 - deduction)

            return {
                "success": True,
                "device_id": device_id,
                "device_name": diagnosis["device_name"],
                "platform": diagnosis["platform"],
                "overall_health_score": health_score,
                "health_grade": health_grade,
                "category_scores": category_scores,
                "total_issues": diagnosis["total_issues"],
                "critical_issues": diagnosis["issues_by_severity"]["critical"],
                "diagnosis_time": diagnosis["diagnosis_time"]
            }

        except Exception as e:
            logger.error("get_device_health_score failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def get_remediation_history(self, device_id: str = None, days: int = 7) -> Dict[str, Any]:
        """
        Get remediation history for device(s).
        """
        logger.info("get_remediation_history", device_id=device_id, days=days)

        # TODO: Implement audit log retrieval
        # This would require a database or storage system to track operations

        return {
            "success": True,
            "device_id": device_id,
            "days": days,
            "history": [],
            "message": "Audit logging system not yet implemented"
        }

    async def export_health_report(
        self,
        format: str = "excel",
        include_devices: list = None,
        report_type: str = "comprehensive"
    ) -> Dict[str, Any]:
        """
        Export device health report.
        """
        logger.info("export_health_report", format=format, report_type=report_type)

        # TODO: Implement report generation
        # This would use openpyxl for Excel or reportlab for PDF

        return {
            "success": True,
            "format": format,
            "report_type": report_type,
            "message": "Report generation not yet implemented",
            "note": "Will generate Excel/PDF reports in future version"
        }

    async def scan_for_issues(self, issue_type: str = "all", severity: str = "all") -> Dict[str, Any]:
        """
        Scan entire fleet for specific types of issues.
        """
        logger.info("scan_for_issues", issue_type=issue_type, severity=severity)

        try:
            # Get all devices
            devices = await self.client.list_managed_devices(limit=1000)

            matching_devices = []

            # Define issue detection logic
            for device in devices:
                device_issues = []

                device_id = device["id"]
                device_name = device.get("deviceName", "Unknown")

                # VPN issues - would need to check VPN configuration status
                if issue_type in ["all", "vpn"]:
                    # Placeholder - would check VPN connectivity
                    pass

                # Disk issues
                if issue_type in ["all", "disk"]:
                    total_storage = device.get("totalStorageSpaceInBytes", 0)
                    free_storage = device.get("freeStorageSpaceInBytes", 0)
                    if total_storage > 0:
                        free_percent = (free_storage / total_storage) * 100
                        if free_percent < 15:
                            device_issues.append({
                                "type": "disk",
                                "severity": "critical" if free_percent < 5 else "high",
                                "description": f"Disk space critically low: {free_percent:.1f}% free",
                                "auto_fixable": True
                            })

                # Network issues
                if issue_type in ["all", "network"]:
                    if not device.get("wiFiMacAddress") and not device.get("ethernetMacAddress"):
                        device_issues.append({
                            "type": "network",
                            "severity": "high",
                            "description": "No network connectivity detected",
                            "auto_fixable": True
                        })

                # Security issues
                if issue_type in ["all", "security"]:
                    if not device.get("isEncrypted", False):
                        device_issues.append({
                            "type": "security",
                            "severity": "critical",
                            "description": "Device encryption not enabled",
                            "auto_fixable": True
                        })

                # Compliance issues
                if issue_type in ["all", "compliance"]:
                    if device.get("complianceState") != "compliant":
                        device_issues.append({
                            "type": "compliance",
                            "severity": "high",
                            "description": f"Device not compliant: {device.get('complianceState')}",
                            "auto_fixable": False
                        })

                # Filter by severity
                if severity != "all":
                    device_issues = [i for i in device_issues if i.get("severity") == severity]

                # Add to results if has matching issues
                if device_issues:
                    matching_devices.append({
                        "device_id": device_id,
                        "device_name": device_name,
                        "platform": device.get("operatingSystem", "Unknown"),
                        "issues": device_issues,
                        "issue_count": len(device_issues)
                    })

            # Sort by issue count (descending)
            matching_devices.sort(key=lambda x: x["issue_count"], reverse=True)

            return {
                "success": True,
                "issue_type": issue_type,
                "severity": severity,
                "total_devices_scanned": len(devices),
                "devices_with_issues": len(matching_devices),
                "devices": matching_devices
            }

        except Exception as e:
            logger.error("scan_for_issues failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def get_endpoint_analytics_performance(self, device_id: str = None) -> Dict[str, Any]:
        """
        Get real-time CPU and RAM performance scores from Endpoint Analytics.
        Returns data on CPU spikes, RAM usage, and startup performance.
        """
        logger.info("get_endpoint_analytics_performance", device_id=device_id)
        try:
            # Query endpoint analytics (beta)
            endpoint = "/deviceManagement/userExperienceAnalyticsDevicePerformance"
            if device_id:
                endpoint += f"?$filter=deviceId eq '{device_id}'"
            
            results = await self.client.get(endpoint, use_beta=True)
            return {
                "success": True,
                "data": results.get("value", []) if not device_id else results
            }
        except Exception as e:
            logger.error("get_endpoint_analytics_performance failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_device_logs(self, device_id: str, log_type: str = "all", hours: int = 24) -> Dict[str, Any]:
        """
        Retrieve device logs from Intune.
        """
        logger.info("get_device_logs", device_id=device_id, log_type=log_type, hours=hours)

        # TODO: Implement log retrieval via Graph API
        # This would query device compliance logs, configuration logs, etc.

        return {
            "success": True,
            "device_id": device_id,
            "log_type": log_type,
            "hours": hours,
            "logs": [],
            "message": "Log retrieval not yet implemented"
        }
