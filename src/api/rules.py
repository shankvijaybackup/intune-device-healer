"""
CRUD for remediation rules (FR-6).

GET    /api/v1/rules        – list all rules (operator)
GET    /api/v1/rules/{id}   – get single rule (operator)
POST   /api/v1/rules        – create rule (admin)
PUT    /api/v1/rules/{id}   – update rule (admin)
DELETE /api/v1/rules/{id}   – delete rule (admin)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import DbSession, require_admin, require_operator
from domain.models import RuleIn, RuleOut
from engine.rule_engine import get_rule_engine
from infra.repositories import RuleRepository

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


def _orm_to_out(row) -> RuleOut:
    from domain.models import Trigger, TriggerCondition, Remediation, RemediationStep, RetryPolicy, Escalation
    trigger = row.trigger if isinstance(row.trigger, dict) else {}
    remediation = row.remediation if isinstance(row.remediation, dict) else {}
    retry = row.retry_policy or {}
    esc = row.escalation

    return RuleOut(
        id=row.id,
        name=row.name,
        description=row.description,
        trigger=Trigger(
            failure_type=trigger.get("failure_type", ""),
            conditions=[TriggerCondition(**c) for c in trigger.get("conditions", [])],
        ),
        remediation=Remediation(
            steps=[RemediationStep(**s) for s in remediation.get("steps", [])],
        ),
        retry_policy=RetryPolicy(**retry),
        escalation=Escalation(**esc) if esc else None,
        priority=row.priority or "medium",
        enabled=row.enabled,
        source=row.source or "api",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[RuleOut])
async def list_rules(
    db: DbSession,
    _: Annotated[dict, Depends(require_operator)],
    enabled_only: bool = False,
):
    repo = RuleRepository(db)
    rows = await repo.list(enabled_only=enabled_only)
    return [_orm_to_out(r) for r in rows]


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(
    rule_id: str,
    db: DbSession,
    _: Annotated[dict, Depends(require_operator)],
):
    repo = RuleRepository(db)
    row = await repo.get(rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _orm_to_out(row)


@router.post("", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    rule_in: RuleIn,
    db: DbSession,
    current_user: Annotated[dict, Depends(require_admin)],
):
    repo = RuleRepository(db)
    row = await repo.upsert({
        "id": rule_in.id,
        "name": rule_in.name,
        "description": rule_in.description,
        "trigger": rule_in.trigger.model_dump(),
        "remediation": rule_in.remediation.model_dump(),
        "retry_policy": rule_in.retry_policy.model_dump(),
        "escalation": rule_in.escalation.model_dump() if rule_in.escalation else None,
        "priority": rule_in.priority,
        "enabled": rule_in.enabled,
        "source": "api",
    })
    # Also update in-memory engine
    get_rule_engine().add_rule(rule_in)
    return _orm_to_out(row)


@router.put("/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: str,
    rule_in: RuleIn,
    db: DbSession,
    _: Annotated[dict, Depends(require_admin)],
):
    if rule_in.id != rule_id:
        raise HTTPException(status_code=400, detail="rule_id in path must match body id")
    repo = RuleRepository(db)
    existing = await repo.get(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    row = await repo.upsert({
        "id": rule_in.id,
        "name": rule_in.name,
        "description": rule_in.description,
        "trigger": rule_in.trigger.model_dump(),
        "remediation": rule_in.remediation.model_dump(),
        "retry_policy": rule_in.retry_policy.model_dump(),
        "escalation": rule_in.escalation.model_dump() if rule_in.escalation else None,
        "priority": rule_in.priority,
        "enabled": rule_in.enabled,
        "source": existing.source,
    })
    get_rule_engine().add_rule(rule_in)
    return _orm_to_out(row)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    db: DbSession,
    _: Annotated[dict, Depends(require_admin)],
):
    repo = RuleRepository(db)
    deleted = await repo.delete(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    get_rule_engine().remove_rule(rule_id)
