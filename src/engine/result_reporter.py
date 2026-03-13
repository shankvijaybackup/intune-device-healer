"""
Result Reporter – posts remediation outcomes back to AtomicWork (FR-5)
and writes an audit log entry to the database.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ATOMICWORK_BASE_URL = os.getenv("ATOMICWORK_API_URL", "")
ATOMICWORK_API_KEY = os.getenv("ATOMICWORK_API_KEY", "")


async def report_to_atomicwork(
    ticket_id: str | None,
    device_id: str,
    job_id: str,
    success: bool,
    rule_name: str | None,
    summary: str,
    logs: str | None = None,
) -> bool:
    """POST remediation outcome to AtomicWork ticket comments."""
    if not ATOMICWORK_BASE_URL or not ATOMICWORK_API_KEY or not ticket_id:
        logger.debug("AtomicWork reporting skipped (no URL/key/ticket_id)")
        return False

    status_emoji = "✅" if success else "❌"
    body = {
        "comment": (
            f"{status_emoji} **Intune Device Healer** – automated remediation "
            f"{'succeeded' if success else 'failed'}.\n\n"
            f"- **Device:** `{device_id}`\n"
            f"- **Job ID:** `{job_id}`\n"
            f"- **Rule:** {rule_name or 'N/A'}\n"
            f"- **Summary:** {summary}\n"
        )
    }
    if logs:
        body["comment"] += f"\n<details><summary>Logs</summary>\n\n```\n{logs[:3000]}\n```\n</details>"

    url = f"{ATOMICWORK_BASE_URL}/api/v1/requests/{ticket_id}/comments"
    headers = {"Authorization": f"Bearer {ATOMICWORK_API_KEY}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code < 300:
                logger.info("AtomicWork comment posted", ticket_id=ticket_id, job_id=job_id)
                return True
            logger.warning("AtomicWork comment failed: %s %s", resp.status_code, resp.text[:200])
            return False
    except Exception as exc:
        logger.warning("AtomicWork report exception: %s", exc)
        return False


async def report_result(
    *,
    device_id: str,
    job_id: str,
    success: bool,
    rule_name: str | None,
    summary: str,
    logs: str | None = None,
    ticket_id: str | None = None,
    audit_repo: Any = None,
) -> None:
    """Unified reporting: AtomicWork + audit log."""
    # 1. AtomicWork
    await report_to_atomicwork(
        ticket_id=ticket_id,
        device_id=device_id,
        job_id=job_id,
        success=success,
        rule_name=rule_name,
        summary=summary,
        logs=logs,
    )

    # 2. Audit log (if repo provided)
    if audit_repo is not None:
        try:
            await audit_repo.create(
                device_id=device_id,
                action=f"remediation_{'success' if success else 'failure'}",
                actor="system",
                job_id=job_id,
                details={"rule_name": rule_name, "summary": summary},
                outcome="success" if success else "failure",
            )
        except Exception as exc:
            logger.warning("Audit log write failed: %s", exc)
