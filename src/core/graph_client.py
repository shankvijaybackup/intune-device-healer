"""
Microsoft Graph API Client
Handles all API interactions with Microsoft Graph
"""

import httpx
import structlog
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = structlog.get_logger()


class GraphAPIError(Exception):
    """Custom exception for Graph API errors"""
    pass


class GraphClient:
    """Client for Microsoft Graph API operations"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.base_url = config.graph_api_base_url
        self.beta_url = config.graph_api_beta_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        use_beta: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Graph API with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            endpoint: API endpoint (without base URL)
            use_beta: Use beta API version instead of v1.0
            **kwargs: Additional arguments for httpx.request

        Returns:
            Response JSON

        Raises:
            GraphAPIError: If API request fails
        """
        base_url = self.beta_url if use_beta else self.base_url
        
        # Ensure base_url ends with / or endpoint starts with /
        if not base_url.endswith("/") and not endpoint.startswith("/"):
            url = f"{base_url}/{endpoint}"
        elif base_url.endswith("/") and endpoint.startswith("/"):
            url = f"{base_url}{endpoint[1:]}"
        else:
            url = f"{base_url}{endpoint}"

        headers = await self.authenticator.get_headers()
        headers.update(kwargs.pop("headers", {}))

        timeout = httpx.Timeout(self.config.operation_timeout, connect=10.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                logger.debug(
                    "graph_api_request",
                    method=method,
                    url=url,
                    use_beta=use_beta
                )

                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    **kwargs
                )

                # Handle successful but empty responses (e.g., 200/204 with no body)
                if response.status_code in [200, 201, 202, 204]:
                    if not response.content:
                        return {"success": True}
                    try:
                        return response.json()
                    except ValueError:
                        return {"success": True, "raw_content": response.text}

                if response.status_code >= 400:
                    error_data = response.json() if response.content else {}
                    error_message = error_data.get("error", {}).get("message", "Unknown error")
                    logger.error(
                        "graph_api_error",
                        status_code=response.status_code,
                        error=error_message,
                        url=url
                    )
                    raise GraphAPIError(f"Graph API error: {error_message} (Status: {response.status_code})")

                return response.json()

        except httpx.TimeoutException as e:
            logger.error("graph_api_timeout", url=url, error=str(e))
            raise
        except Exception as e:
            logger.error("graph_api_exception", url=url, error=str(e))
            raise GraphAPIError(f"Request failed: {str(e)}")

    async def get(self, endpoint: str, use_beta: bool = False, **kwargs) -> Dict[str, Any]:
        """Make GET request"""
        return await self._make_request("GET", endpoint, use_beta, **kwargs)

    async def post(self, endpoint: str, use_beta: bool = False, **kwargs) -> Dict[str, Any]:
        """Make POST request"""
        return await self._make_request("POST", endpoint, use_beta, **kwargs)

    async def patch(self, endpoint: str, use_beta: bool = False, **kwargs) -> Dict[str, Any]:
        """Make PATCH request"""
        return await self._make_request("PATCH", endpoint, use_beta, **kwargs)

    async def delete(self, endpoint: str, use_beta: bool = False, **kwargs) -> Dict[str, Any]:
        """Make DELETE request"""
        return await self._make_request("DELETE", endpoint, use_beta, **kwargs)

    async def get_paged_results(
        self,
        endpoint: str,
        use_beta: bool = False,
        max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all paged results from an API endpoint.

        Args:
            endpoint: API endpoint
            use_beta: Use beta API
            max_results: Maximum number of results to return

        Returns:
            List of all results
        """
        results = []
        next_link = endpoint

        while next_link:
            # If next_link is a full URL (from @odata.nextLink), extract the path
            if next_link.startswith("http"):
                next_link = next_link.split(self.base_url)[-1].split(self.beta_url)[-1]

            response = await self.get(next_link, use_beta=use_beta)

            # Handle both direct arrays and value-wrapped responses
            if isinstance(response, list):
                results.extend(response)
            elif "value" in response:
                results.extend(response["value"])

            # Check for pagination
            next_link = response.get("@odata.nextLink", None)

            # Respect max_results limit
            if max_results and len(results) >= max_results:
                results = results[:max_results]
                break

        logger.debug("paged_results_retrieved", count=len(results))
        return results

    # =========================================================================
    # DEVICE OPERATIONS
    # =========================================================================

    async def list_managed_devices(
        self,
        filter_query: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List all Intune managed devices.

        Args:
            filter_query: OData filter query
            limit: Maximum number of devices

        Returns:
            List of devices
        """
        endpoint = "/deviceManagement/managedDevices"
        if filter_query:
            endpoint += f"?$filter={filter_query}"

        return await self.get_paged_results(endpoint, max_results=limit)

    async def get_device(self, device_id: str) -> Dict[str, Any]:
        """
        Get device details by ID.

        Args:
            device_id: Device ID

        Returns:
            Device information
        """
        return await self.get(f"/deviceManagement/managedDevices/{device_id}")

    async def sync_device(self, device_id: str) -> Dict[str, Any]:
        """Trigger device sync."""
        return await self.post(f"/deviceManagement/managedDevices/{device_id}/syncDevice")

    async def execute_device_action(self, device_id: str, action: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a remote action on a managed device.
        Supported actions: rebootDevice, lockDevice, retire, wipe, 
        requestRemoteAssistance, windowsDefenderScan, etc.
        """
        # 1. Execute the requested action
        endpoint = f"/deviceManagement/managedDevices/{device_id}/{action}"
        result = await self.post(endpoint, **kwargs)
        
        # 2. PROACTIVE: Always trigger a device sync to ensure the action is received "real-time"
        # We don't wait for this to complete as success/failure of the sync is secondary to the action
        logger.info("triggering_realtime_sync", device_id=device_id, action=action)
        try:
            await self.sync_device(device_id)
        except Exception as e:
            logger.warning("sync_failed_after_action", error=str(e))
            
        return result

    async def get_device_compliance_policies(self, device_id: str) -> List[Dict[str, Any]]:
        """Get compliance policies for a device"""
        return await self.get(
            f"/deviceManagement/managedDevices/{device_id}/deviceCompliancePolicyStates"
        )

    async def get_device_configuration_states(self, device_id: str) -> List[Dict[str, Any]]:
        """Get configuration states for a device"""
        return await self.get(
            f"/deviceManagement/managedDevices/{device_id}/deviceConfigurationStates"
        )

    # =========================================================================
    # SCRIPT OPERATIONS
    # =========================================================================

    async def create_device_management_script(
        self,
        display_name: str,
        script_content: str,
        run_as_account: str = "system",
        enforce_signature_check: bool = False
    ) -> Dict[str, Any]:
        """
        Create PowerShell script in Intune.

        Args:
            display_name: Script name
            script_content: Base64 encoded script content
            run_as_account: system or user
            enforce_signature_check: Require signature

        Returns:
            Created script object
        """
        import base64

        payload = {
            "displayName": display_name,
            "description": f"Auto-generated by Intune Device Healer",
            "scriptContent": base64.b64encode(script_content.encode()).decode(),
            "runAsAccount": run_as_account,
            "enforceSignatureCheck": enforce_signature_check,
            "fileName": f"{display_name}.ps1"
        }

        return await self.post(
            "/deviceManagement/deviceManagementScripts",
            json=payload,
            use_beta=True  # Use beta API for script management
        )

    async def assign_script_to_device(
        self,
        script_id: str,
        device_id: str
    ) -> Dict[str, Any]:
        """
        Assign script to specific device.

        Args:
            script_id: Script ID
            device_id: Device ID

        Returns:
            Assignment result
        """
        payload = {
            "deviceManagementScriptAssignments": [
                {
                    "target": {
                        "@odata.type": "#microsoft.graph.deviceManagementScriptDeviceTarget",
                        "deviceId": device_id
                    }
                }
            ]
        }

        result = await self.post(
            f"/deviceManagement/deviceManagementScripts/{script_id}/assign",
            json=payload
        )

        # 2. PROACTIVE: Always trigger a device sync to ensure the script is picked up "real-time"
        logger.info("triggering_realtime_sync_for_script", device_id=device_id, script_id=script_id)
        try:
            await self.sync_device(device_id)
        except Exception as e:
            logger.warning("sync_failed_after_assignment", error=str(e))

        return result

    async def create_device_health_script(
        self,
        display_name: str,
        detection_script: str,
        remediation_script: str,
        run_as_account: str = "system"
    ) -> Dict[str, Any]:
        """
        Create proactive remediation (device health script).

        Args:
            display_name: Script name
            detection_script: Detection script content (base64)
            remediation_script: Remediation script content (base64)
            run_as_account: system or user

        Returns:
            Created health script object
        """
        import base64

        payload = {
            "displayName": display_name,
            "description": "Auto-generated by Intune Device Healer",
            "detectionScriptContent": base64.b64encode(detection_script.encode()).decode(),
            "remediationScriptContent": base64.b64encode(remediation_script.encode()).decode(),
            "runAs32Bit": False,
            "enforceSignatureCheck": False,
            "runAsAccount": run_as_account
        }

        return await self.post(
            "/deviceManagement/deviceHealthScripts",
            use_beta=True,
            json=payload
        )

    async def assign_health_script_to_device(
        self,
        script_id: str,
        device_id: str
    ) -> Dict[str, Any]:
        """
        Assign health script (proactive remediation) to specific device.

        Args:
            script_id: Health script ID
            device_id: Device ID

        Returns:
            Assignment result
        """
        payload = {
            "deviceHealthScriptAssignments": [
                {
                    "target": {
                        "@odata.type": "#microsoft.graph.allDevicesAssignmentTarget"
                    },
                    "runRemediationScript": True,
                    "runSchedule": {
                        "@odata.type": "#microsoft.graph.deviceHealthScriptRunOnceSchedule"
                    }
                }
            ]
        }

        return await self.post(
            f"/deviceManagement/deviceHealthScripts/{script_id}/assign",
            use_beta=True,
            json=payload
        )

    # =========================================================================
    # CONFIGURATION OPERATIONS
    # =========================================================================

    async def list_configuration_policies(self) -> List[Dict[str, Any]]:
        """List all configuration policies"""
        return await self.get_paged_results("/deviceManagement/deviceConfigurations")

    async def list_compliance_policies(self) -> List[Dict[str, Any]]:
        """List all compliance policies"""
        return await self.get_paged_results("/deviceManagement/deviceCompliancePolicies")

    async def create_vpn_configuration(
        self,
        name: str,
        vpn_type: str,
        server_address: str,
        authentication_method: str,
        platform: str = "windows10"
    ) -> Dict[str, Any]:
        """
        Create VPN configuration profile.

        Args:
            name: Profile name
            vpn_type: ikev2, l2tp, pptp, automatic
            server_address: VPN server address
            authentication_method: certificate, usernamePassword
            platform: windows10, macOS

        Returns:
            Created VPN profile
        """
        if platform.lower() == "windows10":
            payload = {
                "@odata.type": "#microsoft.graph.windows10VpnConfiguration",
                "displayName": name,
                "connectionName": name,
                "servers": [
                    {
                        "description": server_address,
                        "address": server_address,
                        "isDefaultServer": True
                    }
                ],
                "connectionType": vpn_type,
                "authenticationMethod": authentication_method
            }
        else:  # macOS
            payload = {
                "@odata.type": "#microsoft.graph.macOSVpnConfiguration",
                "displayName": name,
                "connectionName": name,
                "server": {
                    "description": server_address,
                    "address": server_address
                },
                "connectionType": vpn_type,
                "authenticationMethod": authentication_method
            }

        return await self.post(
            "/deviceManagement/deviceConfigurations",
            json=payload
        )
