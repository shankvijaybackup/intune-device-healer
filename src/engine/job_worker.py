"""
Job Worker – picks up PENDING jobs and executes remediation steps.

Execution model:
  • Each step maps to an MCP tool name (e.g., "fix_windows_updates").
  • The worker calls the corresponding tool function from the tools modules.
  • Retry with exponential back-off up to rule.retry_policy.max_attempts.
  • On exhausting retries, marks job ESCALATED.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
from typing import Any, Callable

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from domain.models import JobStatus, RuleIn
from infra.metrics import (
    job_duration_seconds,
    jobs_failed,
    jobs_in_flight,
    jobs_success,
    jobs_total,
)

logger = structlog.get_logger()

# Registry mapping MCP tool name → callable loaded lazily
_TOOL_REGISTRY: dict[str, Callable] = {}


def _load_tool(tool_name: str) -> Callable | None:
    """Look up a tool function by name across tool modules."""
    if tool_name in _TOOL_REGISTRY:
        return _TOOL_REGISTRY[tool_name]
    # Try to import from server module (where @mcp.tool wrappers live)
    try:
        import server as srv
        fn = getattr(srv, tool_name, None)
        if fn is not None:
            _TOOL_REGISTRY[tool_name] = fn
            return fn
    except ImportError:
        pass
    logger.warning("Tool not found in registry", tool_name=tool_name)
    return None


async def _execute_step(tool_name: str, params: dict[str, Any]) -> dict:
    """Call a single tool function and return its result."""
    fn = _load_tool(tool_name)
    if fn is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    result = await fn(**params)
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(f"Tool {tool_name} returned error: {result['error']}")
    return result if isinstance(result, dict) else {"output": str(result)}


async def execute_job(
    *,
    job_id: str,
    device_id: str,
    rule: RuleIn,
    job_repo: Any,
    audit_repo: Any,
    ticket_id: str | None = None,
) -> dict:
    """
    Execute all remediation steps for a job with retry logic.
    Returns a result dict with success flag and step outputs.
    """
    from engine.result_reporter import report_result

    step_results: list[dict] = []
    log_lines: list[str] = []
    start_time = time.monotonic()
    rule_id = rule.id
    max_attempts = rule.retry_policy.max_attempts
    delay = rule.retry_policy.initial_delay_seconds
    multiplier = rule.retry_policy.backoff_multiplier

    jobs_total.labels(rule_id=rule_id).inc()
    jobs_in_flight.inc()

    try:
        await job_repo.set_running(job_id)

        for attempt in range(1, max_attempts + 1):
            step_results.clear()
            log_lines.clear()
            log_lines.append(f"=== Attempt {attempt}/{max_attempts} ===")
            success = True

            for idx, step in enumerate(rule.remediation.steps):
                tool_name = step.tool
                params = dict(step.params)
                params.setdefault("device_id", device_id)

                log_lines.append(f"[{idx+1}] Running {tool_name}({params})")
                try:
                    result = await _execute_step(tool_name, params)
                    step_results.append({"step": tool_name, "status": "ok", "result": result})
                    log_lines.append(f"    ✓ {tool_name} succeeded")
                    await job_repo.increment_step(job_id)
                except Exception as exc:
                    step_results.append({"step": tool_name, "status": "error", "error": str(exc)})
                    log_lines.append(f"    ✗ {tool_name} failed: {exc}")
                    success = False
                    break  # abort remaining steps on failure

            if success:
                break

            if attempt < max_attempts:
                sleep_for = delay * (multiplier ** (attempt - 1))
                log_lines.append(f"Retrying in {sleep_for:.0f}s …")
                await asyncio.sleep(sleep_for)

        duration = time.monotonic() - start_time
        job_duration_seconds.labels(rule_id=rule_id).observe(duration)

        log_str = "\n".join(log_lines)
        summary = (
            f"Completed {len(rule.remediation.steps)} steps in {duration:.1f}s"
            if success
            else f"Failed after {max_attempts} attempts"
        )

        if success:
            jobs_success.labels(rule_id=rule_id).inc()
            await job_repo.set_done(
                job_id, success=True,
                result={"steps": step_results},
                logs=log_str,
            )
        else:
            jobs_failed.labels(rule_id=rule_id).inc()
            if rule.escalation:
                await job_repo.set_escalated(job_id)
                log_lines.append(f"Job escalated: {rule.escalation.action}")
                log_str = "\n".join(log_lines)
                summary = f"Escalated after {max_attempts} failed attempts"
            else:
                await job_repo.set_done(
                    job_id, success=False,
                    result={"steps": step_results},
                    logs=log_str,
                    error="All retry attempts exhausted",
                )

        await report_result(
            device_id=device_id,
            job_id=job_id,
            success=success,
            rule_name=rule.name,
            summary=summary,
            logs=log_str,
            ticket_id=ticket_id,
            audit_repo=audit_repo,
        )

        return {"success": success, "steps": step_results, "duration_seconds": duration}

    except Exception as exc:
        logger.exception("Unexpected job execution error", job_id=job_id, error=str(exc))
        jobs_failed.labels(rule_id=rule_id).inc()
        await job_repo.set_done(job_id, success=False, error=str(exc))
        return {"success": False, "error": str(exc)}
    finally:
        jobs_in_flight.dec()
