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

import base64

@router.post("")
async def update_config(payload: ConfigUpdate, request: Request):
    """
    Update system configuration and return deployment instructions.
    Expects Base64 encoded sensitive fields.
    """
    try:
        def decode_field(encoded_str: str) -> str:
            try:
                # Basic Base64 decoding
                return base64.b64decode(encoded_str).decode("utf-8")
            except Exception:
                # Fallback if already decoded or malformed
                return encoded_str

        # Decode fields
        decoded_url = payload.atomicworkUrl
        decoded_key = decode_field(payload.atomicworkApiKey)
        decoded_client_id = decode_field(payload.azureClientId)
        decoded_tenant_id = decode_field(payload.azureTenantId)
        decoded_secret = decode_field(payload.azureClientSecret)

        # Update settings object
        settings.atomicwork_base_url = decoded_url
        settings.atomicwork_api_key = decoded_key
        settings.azure_client_id = decoded_client_id
        settings.azure_tenant_id = decoded_tenant_id
        settings.azure_client_secret = decoded_secret

        # Persist to .env for next restart
        env_path = os.path.join(os.getcwd(), ".env")
        with open(env_path, "a") as f:
            f.write(f"\n# Updated via Dashboard (Zero-Visibility Loop)\n")
            f.write(f"ATOMICWORK_BASE_URL=\"{decoded_url}\"\n")
            f.write(f"ATOMICWORK_API_KEY=\"{decoded_key}\"\n")
            f.write(f"AZURE_CLIENT_ID=\"{decoded_client_id}\"\n")
            f.write(f"AZURE_TENANT_ID=\"{decoded_tenant_id}\"\n")
            f.write(f"AZURE_CLIENT_SECRET=\"{decoded_secret}\"\n")

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
