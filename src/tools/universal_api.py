"""
Universal API Tools for Microsoft Graph and Azure Resource Management
"""

import os
from typing import Optional, Dict, Any, List
import httpx
import structlog

logger = structlog.get_logger()

class UniversalApiTools:
    """Tools for arbitrary API calls to Microsoft services"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.graph_base_url = "https://graph.microsoft.com"
        self.arm_base_url = "https://management.azure.com"

    async def call_microsoft_api(
        self,
        api_type: str,
        path: str,
        method: str = "GET",
        api_version: Optional[str] = None,
        subscription_id: Optional[str] = None,
        query_params: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        graph_api_version: str = "v1.0",
        fetch_all: bool = False,
        consistency_level: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Execute direct API calls to Microsoft Graph or Azure Resource Management.
        """
        headers = await self.authenticator.get_headers()
        
        if consistency_level:
            headers["ConsistencyLevel"] = consistency_level

        if api_type.lower() == "graph":
            url = f"{self.graph_base_url}/{graph_api_version}/{path.lstrip('/')}"
        else:
            if not subscription_id:
                subscription_id = self.config.azure_subscription_id
            if not api_version:
                return {"success": False, "error": "api_version is required for Azure ARM calls"}
            
            url = f"{self.arm_base_url}/subscriptions/{subscription_id}/{path.lstrip('/')}?api-version={api_version}"

        async with httpx.AsyncClient(timeout=float(timeout)) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=query_params,
                    json=body
                )
                
                response.raise_for_status()
                data = response.json()

                # Handle pagination if fetch_all is True
                if fetch_all and "value" in data and "@odata.nextLink" in data:
                    all_values = data["value"]
                    next_link = data["@odata.nextLink"]
                    while next_link:
                        next_resp = await client.get(next_link, headers=headers)
                        next_resp.raise_for_status()
                        next_data = next_resp.json()
                        all_values.extend(next_data.get("value", []))
                        next_link = next_data.get("@odata.nextLink")
                    data["value"] = all_values

                return {"success": True, "data": data}
            except httpx.HTTPStatusError as e:
                return {
                    "success": False, 
                    "error": f"HTTP {e.response.status_code}", 
                    "detail": e.response.text
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def execute_graph_batch(self, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute multiple Graph API requests in one batch"""
        url = f"{self.graph_base_url}/v1.0/$batch"
        headers = await self.authenticator.get_headers()
        
        payload = {"requests": requests}
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"success": True, "data": response.json()}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def execute_delta_query(self, resource: str, delta_token: Optional[str] = None) -> Dict[str, Any]:
        """Track incremental changes via delta query"""
        path = f"{resource.strip('/')}/delta"
        params = {"$deltatoken": delta_token} if delta_token else {}
        return await self.call_microsoft_api("graph", path, query_params=params)

    async def execute_graph_search(self, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Search M365 content via /search/query"""
        path = "search/query"
        payload = {"requests": requests}
        return await self.call_microsoft_api("graph", path, method="POST", body=payload)
