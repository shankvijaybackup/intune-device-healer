"""
Main API router – mounts all sub-routers.
"""

from fastapi import APIRouter

from api.auth import router as auth_router
from api.webhook import router as webhook_router
from api.devices import router as devices_router
from api.jobs import router as jobs_router
from api.rules import router as rules_router
from api.config import router as config_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(webhook_router)
api_router.include_router(devices_router)
api_router.include_router(jobs_router)
api_router.include_router(rules_router)
api_router.include_router(config_router)
