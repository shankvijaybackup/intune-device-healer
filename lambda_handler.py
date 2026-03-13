"""
AWS Lambda Handler for Intune Device Healer
Wraps the FastAPI application for Lambda execution
"""

import sys
import os

# Add src directory to path so all tool modules resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mangum import Mangum
from server import app  # Import unified app from server.py which has both Webhook and MCP

# Create Lambda handler using Mangum adapter
# Mangum converts API Gateway events to ASGI requests
# api_gateway_base_path strips /prod stage from path before routing to FastAPI
# api_gateway_base_path tells Mangum to strip /prod from incoming paths before routing.
# This also sets root_path=/prod in the ASGI scope, so any redirects Starlette generates
# will include /prod — preventing the redirect loop on /mcp -> /mcp/.
handler = Mangum(app, lifespan="off")


def lambda_handler(event, context):
    """
    AWS Lambda entry point

    Args:
        event: API Gateway event (HTTP request)
        context: Lambda context

    Returns:
        API Gateway response
    """
    return handler(event, context)
