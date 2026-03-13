"""
GET  /api/v1/jobs          – list jobs
GET  /api/v1/jobs/{job_id} – job detail + logs
POST /api/v1/jobs/{job_id}/retry – re-run a failed job
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from api.deps import DbSession, require_operator, require_viewer
from domain.models import JobOut, JobStatus
from engine.job_worker import execute_job
from engine.rule_engine import get_rule_engine
from infra.database import get_db_session
from infra.repositories import AuditLogRepository, JobRepository

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
async def list_jobs(
    db: DbSession,
    _: Annotated[dict, Depends(require_viewer)],
    device_id: Optional[str] = Query(None),
    job_status: Optional[JobStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    repo = JobRepository(db)
    jobs = await repo.list(device_id=device_id, status=job_status, limit=limit, offset=offset)
    return jobs


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    db: DbSession,
    _: Annotated[dict, Depends(require_viewer)],
):
    repo = JobRepository(db)
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    job_id: str,
    db: DbSession,
    background_tasks: BackgroundTasks,
    current_user: Annotated[dict, Depends(require_operator)],
):
    """Manually re-trigger a failed or escalated job (US-006)."""
    repo = JobRepository(db)
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.FAILED, JobStatus.ESCALATED):
        raise HTTPException(status_code=400, detail=f"Job status is {job.status}, not retryable")

    engine = get_rule_engine()
    rule = engine.get_rule(job.rule_id) if job.rule_id else None
    if not rule:
        raise HTTPException(status_code=400, detail=f"Rule '{job.rule_id}' not found in engine")

    audit_repo = AuditLogRepository(db)
    await audit_repo.create(
        device_id=job.device_id,
        action="job_manual_retry",
        actor=current_user["username"],
        job_id=job_id,
        details={"rule_id": job.rule_id},
    )

    async def _run():
        async with get_db_session() as s:
            await execute_job(
                job_id=job_id,
                device_id=job.device_id,
                rule=rule,
                job_repo=JobRepository(s),
                audit_repo=AuditLogRepository(s),
            )

    background_tasks.add_task(_run)
    return {"accepted": True, "job_id": job_id}
