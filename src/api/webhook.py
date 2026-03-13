"""
POST /api/v1/webhook  – ingest compliance failure events from AtomicWork (FR-1).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from api.deps import DbSession, get_current_user
from domain.models import WebhookEventIn
from engine.job_worker import execute_job
from engine.rule_engine import get_rule_engine
from infra.database import get_db_session
from infra.metrics import webhook_events_total
from infra.repositories import AuditLogRepository, EventRepository, JobRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["webhook"])


async def _process_event(event_id: str, device_id: str,
                          failure_type: str, details: dict | None) -> None:
    """Background task: match rule → create job → execute."""
    engine = get_rule_engine()
    rule = engine.match(failure_type, details)

    if rule is None:
        logger.info("No rule matched for failure_type=%s device=%s", failure_type, device_id)
        return

    async with get_db_session() as session:
        job_repo = JobRepository(session)
        audit_repo = AuditLogRepository(session)

        job = await job_repo.create(
            device_id=device_id,
            event_id=event_id,
            rule_id=rule.id,
            rule_name=rule.name,
            max_attempts=rule.retry_policy.max_attempts,
            steps_total=len(rule.remediation.steps),
        )
        await audit_repo.create(
            device_id=device_id,
            action="job_created",
            job_id=job.id,
            details={"rule_id": rule.id, "failure_type": failure_type},
        )

    # Execute outside the session (job worker opens its own sessions)
    async with get_db_session() as session:
        job_repo = JobRepository(session)
        audit_repo = AuditLogRepository(session)
        await execute_job(
            job_id=job.id,
            device_id=device_id,
            rule=rule,
            job_repo=job_repo,
            audit_repo=audit_repo,
        )


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    payload: WebhookEventIn,
    background_tasks: BackgroundTasks,
    db: DbSession,
):
    """
    Accepts a compliance failure event and triggers remediation asynchronously.
    No JWT required – use network-level controls or add API-key header in prod.
    """
    webhook_events_total.labels(failure_type=payload.failureType).inc()

    ts = payload.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    event_repo = EventRepository(db)
    event = await event_repo.create(
        device_id=payload.deviceId,
        failure_type=payload.failureType,
        timestamp=ts,
        details=payload.details,
        raw_payload=payload.model_dump(mode="json"),
    )

    background_tasks.add_task(
        _process_event,
        event_id=event.id,
        device_id=payload.deviceId,
        failure_type=payload.failureType,
        details=payload.details,
    )

    return {
        "accepted": True,
        "event_id": event.id,
        "device_id": payload.deviceId,
        "failure_type": payload.failureType,
    }
