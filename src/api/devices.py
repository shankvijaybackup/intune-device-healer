"""
GET /api/v1/devices  – list Intune devices with compliance state (FR-6).
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from api.deps import require_viewer
from core.auth import GraphAuthenticator
from core.config import settings

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])

def get_auth():
    return GraphAuthenticator(settings)


@router.get("")
async def list_devices(
    _: Annotated[dict, Depends(require_viewer)],
    top: int = Query(100, ge=1, le=999),
    filter_compliance: Optional[str] = Query(None, description="compliant | noncompliant | unknown"),
):
    """
    Proxy to MS Graph – returns managed device list with compliance state.
    """
    token = await get_auth().get_access_token()
    import httpx

    params: dict = {"$top": top, "$select": "id,deviceName,operatingSystem,complianceState,lastSyncDateTime,userPrincipalName,managedDeviceOwnerType"}
    if filter_compliance:
        params["$filter"] = f"complianceState eq '{filter_compliance}'"

    headers = {"Authorization": f"Bearer {token}"}
    url = f"{settings.graph_api_base_url}/deviceManagement/managedDevices"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    return {
        "total": len(data.get("value", [])),
        "devices": data.get("value", []),
        "nextLink": data.get("@odata.nextLink"),
    }
