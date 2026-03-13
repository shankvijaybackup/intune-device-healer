"""
Repository layer – all DB read/write operations for Jobs, Events, Rules, AuditLogs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import AuditLogORM, EventORM, JobORM, JobStatus, RuleORM


# ── Events ────────────────────────────────────────────────────────────────────

class EventRepository:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def create(self, device_id: str, failure_type: str,
                     timestamp: datetime, details: dict | None,
                     raw_payload: dict | None = None) -> EventORM:
        event = EventORM(
            id=str(uuid.uuid4()),
            device_id=device_id,
            failure_type=failure_type,
            timestamp=timestamp,
            details=details,
            raw_payload=raw_payload,
        )
        self._s.add(event)
        await self._s.flush()
        return event


# ── Jobs ──────────────────────────────────────────────────────────────────────

class JobRepository:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def create(self, device_id: str, event_id: str | None,
                     rule_id: str | None, rule_name: str | None,
                     max_attempts: int = 3, steps_total: int = 0) -> JobORM:
        job = JobORM(
            id=str(uuid.uuid4()),
            device_id=device_id,
            event_id=event_id,
            rule_id=rule_id,
            rule_name=rule_name,
            status=JobStatus.PENDING,
            max_attempts=max_attempts,
            steps_total=steps_total,
        )
        self._s.add(job)
        await self._s.flush()
        return job

    async def get(self, job_id: str) -> Optional[JobORM]:
        result = await self._s.execute(select(JobORM).where(JobORM.id == job_id))
        return result.scalar_one_or_none()

    async def list(self, device_id: str | None = None,
                   status: JobStatus | None = None,
                   limit: int = 50, offset: int = 0) -> list[JobORM]:
        q = select(JobORM).order_by(JobORM.created_at.desc()).limit(limit).offset(offset)
        if device_id:
            q = q.where(JobORM.device_id == device_id)
        if status:
            q = q.where(JobORM.status == status)
        result = await self._s.execute(q)
        return list(result.scalars().all())

    async def set_running(self, job_id: str) -> None:
        await self._s.execute(
            update(JobORM)
            .where(JobORM.id == job_id)
            .values(status=JobStatus.RUNNING, started_at=datetime.now(timezone.utc))
        )

    async def set_done(self, job_id: str, success: bool,
                       result: dict | None = None,
                       logs: str | None = None,
                       error: str | None = None) -> None:
        status = JobStatus.SUCCESS if success else JobStatus.FAILED
        await self._s.execute(
            update(JobORM)
            .where(JobORM.id == job_id)
            .values(
                status=status,
                result=result,
                logs=logs,
                error=error,
                finished_at=datetime.now(timezone.utc),
            )
        )

    async def increment_step(self, job_id: str) -> None:
        job = await self.get(job_id)
        if job:
            await self._s.execute(
                update(JobORM)
                .where(JobORM.id == job_id)
                .values(steps_done=job.steps_done + 1)
            )

    async def set_escalated(self, job_id: str) -> None:
        await self._s.execute(
            update(JobORM)
            .where(JobORM.id == job_id)
            .values(status=JobStatus.ESCALATED, finished_at=datetime.now(timezone.utc))
        )


# ── Audit Logs ────────────────────────────────────────────────────────────────

class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def create(self, device_id: str, action: str,
                     actor: str = "system",
                     job_id: str | None = None,
                     details: dict | None = None,
                     outcome: str | None = None) -> AuditLogORM:
        log = AuditLogORM(
            id=str(uuid.uuid4()),
            job_id=job_id,
            device_id=device_id,
            action=action,
            actor=actor,
            details=details,
            outcome=outcome,
        )
        self._s.add(log)
        await self._s.flush()
        return log

    async def list(self, device_id: str | None = None,
                   job_id: str | None = None,
                   limit: int = 100, offset: int = 0) -> list[AuditLogORM]:
        q = (select(AuditLogORM)
             .order_by(AuditLogORM.created_at.desc())
             .limit(limit).offset(offset))
        if device_id:
            q = q.where(AuditLogORM.device_id == device_id)
        if job_id:
            q = q.where(AuditLogORM.job_id == job_id)
        result = await self._s.execute(q)
        return list(result.scalars().all())

    async def purge_old(self, before: datetime) -> int:
        result = await self._s.execute(
            delete(AuditLogORM).where(AuditLogORM.created_at < before)
        )
        return result.rowcount


# ── Rules ─────────────────────────────────────────────────────────────────────

class RuleRepository:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def upsert(self, rule_data: dict) -> RuleORM:
        existing = await self.get(rule_data["id"])
        if existing:
            for k, v in rule_data.items():
                setattr(existing, k, v)
            rule = existing
        else:
            rule = RuleORM(**rule_data)
            self._s.add(rule)
        await self._s.flush()
        return rule

    async def get(self, rule_id: str) -> Optional[RuleORM]:
        result = await self._s.execute(select(RuleORM).where(RuleORM.id == rule_id))
        return result.scalar_one_or_none()

    async def list(self, enabled_only: bool = False) -> list[RuleORM]:
        q = select(RuleORM).order_by(RuleORM.priority)
        if enabled_only:
            q = q.where(RuleORM.enabled.is_(True))
        result = await self._s.execute(q)
        return list(result.scalars().all())

    async def delete(self, rule_id: str) -> bool:
        result = await self._s.execute(
            delete(RuleORM).where(RuleORM.id == rule_id)
        )
        return result.rowcount > 0
