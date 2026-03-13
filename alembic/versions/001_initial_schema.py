"""Initial schema – events, jobs, audit_logs, rules

Revision ID: 001
Revises:
Create Date: 2026-03-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(255), nullable=False, index=True),
        sa.Column("failure_type", sa.String(255), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", JSON, nullable=True),
        sa.Column("raw_payload", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), nullable=True, index=True),
        sa.Column("device_id", sa.String(255), nullable=False, index=True),
        sa.Column("rule_id", sa.String(255), nullable=True),
        sa.Column("rule_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("attempt", sa.Integer, default=1),
        sa.Column("max_attempts", sa.Integer, default=3),
        sa.Column("steps_total", sa.Integer, default=0),
        sa.Column("steps_done", sa.Integer, default=0),
        sa.Column("result", JSON, nullable=True),
        sa.Column("logs", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), nullable=True, index=True),
        sa.Column("device_id", sa.String(255), nullable=False, index=True),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("details", JSON, nullable=True),
        sa.Column("outcome", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "rules",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("trigger", JSON, nullable=False),
        sa.Column("remediation", JSON, nullable=False),
        sa.Column("retry_policy", JSON, nullable=True),
        sa.Column("escalation", JSON, nullable=True),
        sa.Column("priority", sa.String(50), default="medium"),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("source", sa.String(50), default="yaml"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )


def downgrade():
    op.drop_table("rules")
    op.drop_table("audit_logs")
    op.drop_table("jobs")
    op.drop_table("events")
