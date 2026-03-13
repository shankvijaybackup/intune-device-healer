"""
Azure Management Tools for DevOps and Cost Analysis
"""

from typing import Optional, Dict, Any, List
import structlog
from tools.universal_api import UniversalApiTools

logger = structlog.get_logger()

class AzureMgmtTools:
    """Tools for managing Azure resources and costs"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.api = UniversalApiTools(authenticator, config)

    async def get_subscription_overview(self, subscription_id: Optional[str] = None) -> Dict[str, Any]:
        """Get an inventory of resources in the subscription"""
        sub_id = subscription_id or self.config.azure_subscription_id
        if not sub_id:
            return {"success": False, "error": "Subscription ID is required"}
            
        path = "resources"
        # Azure ARM requires api-version
        return await self.api.call_microsoft_api(
            "arm", path, api_version="2021-04-01", subscription_id=sub_id
        )

    async def get_cost_analysis(self, subscription_id: Optional[str] = None, timeframe: str = "BillingMonthToDate") -> Dict[str, Any]:
        """Get actual and forecast spending data"""
        sub_id = subscription_id or self.config.azure_subscription_id
        if not sub_id:
            return {"success": False, "error": "Subscription ID is required"}

        # API: https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage
        path = f"providers/Microsoft.CostManagement/query"
        body = {
            "type": "ActualCost",
            "timeframe": timeframe,
            "dataset": {
                "granularity": "Daily",
                "aggregation": {
                    "totalCost": {"name": "PreTaxCost", "function": "Sum"}
                },
                "grouping": [
                    {"type": "Dimension", "name": "ResourceGroup"},
                    {"type": "Dimension", "name": "ServiceName"}
                ]
            }
        }
        
        return await self.api.call_microsoft_api(
            "arm", path, method="POST", api_version="2021-10-01", subscription_id=sub_id, body=body
        )

    async def list_resource_groups(self, subscription_id: Optional[str] = None) -> Dict[str, Any]:
        """List all resource groups in the subscription"""
        sub_id = subscription_id or self.config.azure_subscription_id
        if not sub_id:
            return {"success": False, "error": "Subscription ID is required"}
            
        return await self.api.call_microsoft_api(
            "arm", "resourcegroups", api_version="2021-04-01", subscription_id=sub_id
        )
