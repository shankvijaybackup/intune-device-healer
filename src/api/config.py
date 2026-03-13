from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from core.config import settings
import os

router = APIRouter(prefix="/api/v1/config", tags=["config"])

class ConfigUpdate(BaseModel):
    atomicworkUrl: str
    atomicworkApiKey: str
    azureClientId: str
    azureTenantId: str
    azureClientSecret: str

@router.post("")
async def update_config(payload: ConfigUpdate, request: Request):
    """
    Update system configuration and return deployment instructions.
    """
    try:
        # Update settings object
        settings.atomicwork_base_url = payload.atomicworkUrl
        settings.atomicwork_api_key = payload.atomicworkApiKey
        settings.azure_client_id = payload.azureClientId
        settings.azure_tenant_id = payload.azureTenantId
        settings.azure_client_secret = payload.azureClientSecret

        # Persist to .env for next restart
        env_path = os.path.join(os.getcwd(), ".env")
        with open(env_path, "a") as f:
            f.write(f"\n# Updated via Dashboard\n")
            f.write(f"ATOMICWORK_BASE_URL=\"{payload.atomicworkUrl}\"\n")
            f.write(f"ATOMICWORK_API_KEY=\"{payload.atomicworkApiKey}\"\n")
            f.write(f"AZURE_CLIENT_ID=\"{payload.azureClientId}\"\n")
            f.write(f"AZURE_TENANT_ID=\"{payload.azureTenantId}\"\n")
            f.write(f"AZURE_CLIENT_SECRET=\"{payload.azureClientSecret}\"\n")

        # Calculate Webhook details
        base_url = str(request.base_url).rstrip("/")
        webhook_url = f"{base_url}/webhook/ticket"
        
        return {
            "status": "success",
            "message": "Configuration updated and persisted",
            "deployment": {
                "webhook_url": webhook_url,
                "payload_format": {
                    "display_id": "DWINC-1234",
                    "event_type": "ticket_created"
                },
                "instructions": "Configure your Atomicwork webhook to hit this URL. The engine will autonomously use MCP skills (diagnostics, remediations) to handle the device associated with the ticket."
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
