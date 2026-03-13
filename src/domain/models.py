"""
Domain models – Pydantic (API layer) and SQLAlchemy ORM (persistence layer).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase


# ── SQLAlchemy base ───────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Enumerations ─────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ESCALATED = "escalated"


class UserRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


# ── ORM Tables ───────────────────────────────────────────────────────────────

class EventORM(Base):
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(255), nullable=False, index=True)
    failure_type = Column(String(255), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    details = Column(JSON, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class JobORM(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(36), nullable=True, index=True)
    device_id = Column(String(255), nullable=False, index=True)
    rule_id = Column(String(255), nullable=True)
    rule_name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default=JobStatus.PENDING)
    attempt = Column(Integer, default=1)
    max_attempts = Column(Integer, default=3)
    steps_total = Column(Integer, default=0)
    steps_done = Column(Integer, default=0)
    result = Column(JSON, nullable=True)
    logs = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class AuditLogORM(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), nullable=True, index=True)
    device_id = Column(String(255), nullable=False, index=True)
    action = Column(String(255), nullable=False)
    actor = Column(String(255), nullable=True)  # "system" | username
    details = Column(JSON, nullable=True)
    outcome = Column(String(50), nullable=True)   # success | failure
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RuleORM(Base):
    __tablename__ = "rules"

    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    trigger = Column(JSON, nullable=False)
    remediation = Column(JSON, nullable=False)
    retry_policy = Column(JSON, nullable=True)
    escalation = Column(JSON, nullable=True)
    priority = Column(String(50), default="medium")
    enabled = Column(Boolean, default=True)
    source = Column(String(50), default="yaml")   # "yaml" | "api"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SystemConfigORM(Base):
    __tablename__ = "system_configs"

    key = Column(String(255), primary_key=True)  # e.g., "atomicwork_api_key"
    value = Column(Text, nullable=True)
    description = Column(String(500), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Pydantic Schemas (API I/O) ────────────────────────────────────────────────

class WebhookEventIn(BaseModel):
    deviceId: str
    failureType: str
    timestamp: datetime
    details: Optional[dict[str, Any]] = None


class JobOut(BaseModel):
    id: str
    event_id: Optional[str]
    device_id: str
    rule_id: Optional[str]
    rule_name: Optional[str]
    status: JobStatus
    attempt: int
    max_attempts: int
    steps_total: int
    steps_done: int
    result: Optional[dict[str, Any]]
    logs: Optional[str]
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class RetryPolicy(BaseModel):
    max_attempts: int = 3
    initial_delay_seconds: int = 30
    backoff_multiplier: float = 2.0


class Escalation(BaseModel):
    after_attempts: int = 3
    action: str = "notify_admin"


class RemediationStep(BaseModel):
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)


class Remediation(BaseModel):
    steps: list[RemediationStep]


class TriggerCondition(BaseModel):
    field: str
    operator: str   # eq | neq | gt | gte | lt | lte | contains
    value: Any


class Trigger(BaseModel):
    failure_type: str
    conditions: list[TriggerCondition] = Field(default_factory=list)


class RuleIn(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    trigger: Trigger
    remediation: Remediation
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    escalation: Optional[Escalation] = None
    priority: str = "medium"
    enabled: bool = True


class RuleOut(RuleIn):
    source: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AuditLogOut(BaseModel):
    id: str
    job_id: Optional[str]
    device_id: str
    action: str
    actor: Optional[str]
    details: Optional[dict[str, Any]]
    outcome: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
