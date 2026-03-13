"""
Rule Engine – loads rules from rules.yaml (and DB), matches incoming events.

Matching logic:
  1. failure_type must equal rule.trigger.failure_type (exact match)
  2. All conditions in rule.trigger.conditions must pass

Supported operators: eq, neq, gt, gte, lt, lte, contains, exists
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from domain.models import RuleIn, Trigger, TriggerCondition, Remediation, RemediationStep, RetryPolicy, Escalation

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _get_nested(obj: dict, field: str) -> Any:
    """Traverse dot-separated field path in a dict."""
    parts = field.split(".")
    cur = obj
    for p in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _evaluate_condition(condition: TriggerCondition, details: dict | None) -> bool:
    details = details or {}
    actual = _get_nested(details, condition.field)
    expected = condition.value

    match condition.operator:
        case "eq":
            return actual == expected
        case "neq":
            return actual != expected
        case "gt":
            return actual is not None and actual > expected
        case "gte":
            return actual is not None and actual >= expected
        case "lt":
            return actual is not None and actual < expected
        case "lte":
            return actual is not None and actual <= expected
        case "contains":
            return expected in (actual or "")
        case "exists":
            return actual is not None
        case _:
            logger.warning("Unknown operator: %s", condition.operator)
            return False


def _rule_from_dict(d: dict) -> RuleIn:
    trigger_raw = d.get("trigger", {})
    trigger = Trigger(
        failure_type=trigger_raw.get("failure_type", ""),
        conditions=[
            TriggerCondition(**c) for c in trigger_raw.get("conditions", [])
        ],
    )
    remediation_raw = d.get("remediation", {})
    remediation = Remediation(
        steps=[RemediationStep(**s) for s in remediation_raw.get("steps", [])]
    )
    retry_raw = d.get("retry_policy", {})
    retry = RetryPolicy(**retry_raw) if retry_raw else RetryPolicy()
    esc_raw = d.get("escalation")
    escalation = Escalation(**esc_raw) if esc_raw else None

    return RuleIn(
        id=d["id"],
        name=d.get("name", d["id"]),
        description=d.get("description"),
        trigger=trigger,
        remediation=remediation,
        retry_policy=retry,
        escalation=escalation,
        priority=d.get("priority", "medium"),
        enabled=d.get("enabled", True),
    )


class RuleEngine:
    """Holds the active rule set and provides event matching."""

    def __init__(self):
        self._rules: list[RuleIn] = []

    # ── Loading ───────────────────────────────────────────────────────────────

    def load_from_file(self, path: str | Path) -> int:
        """Load rules from a YAML file.  Returns count loaded."""
        p = Path(path)
        if not p.exists():
            logger.warning("rules.yaml not found at %s – skipping", p)
            return 0
        with p.open("r") as f:
            data = yaml.safe_load(f) or {}
        raw_rules = data.get("rules", [])
        loaded = [_rule_from_dict(r) for r in raw_rules]
        self._merge(loaded, source="yaml")
        logger.info("Loaded %d rules from %s", len(loaded), p)
        return len(loaded)

    def load_from_db_rows(self, rows: list) -> int:
        """Accept RuleORM rows, convert to RuleIn and merge."""
        loaded = []
        for row in rows:
            try:
                r = RuleIn(
                    id=row.id,
                    name=row.name,
                    description=row.description,
                    trigger=Trigger(**row.trigger) if isinstance(row.trigger, dict) else row.trigger,
                    remediation=Remediation(**row.remediation) if isinstance(row.remediation, dict) else row.remediation,
                    retry_policy=RetryPolicy(**(row.retry_policy or {})),
                    escalation=Escalation(**(row.escalation or {})) if row.escalation else None,
                    priority=row.priority or "medium",
                    enabled=row.enabled,
                )
                loaded.append(r)
            except Exception as exc:
                logger.warning("Skipping invalid rule %s from DB: %s", row.id, exc)
        self._merge(loaded, source="db")
        return len(loaded)

    def _merge(self, incoming: list[RuleIn], source: str) -> None:
        existing_ids = {r.id for r in self._rules}
        for rule in incoming:
            if rule.id in existing_ids:
                self._rules = [r if r.id != rule.id else rule for r in self._rules]
            else:
                self._rules.append(rule)
        # Sort by priority
        self._rules.sort(key=lambda r: PRIORITY_ORDER.get(r.priority, 99))

    def add_rule(self, rule: RuleIn) -> None:
        self._merge([rule], source="api")

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.id != rule_id]
        return len(self._rules) < before

    # ── Matching ──────────────────────────────────────────────────────────────

    def match(self, failure_type: str, details: dict | None = None) -> Optional[RuleIn]:
        """Return the highest-priority matching enabled rule, or None."""
        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.trigger.failure_type != failure_type:
                continue
            if all(_evaluate_condition(c, details) for c in rule.trigger.conditions):
                return rule
        return None

    def all_rules(self) -> list[RuleIn]:
        return list(self._rules)

    def get_rule(self, rule_id: str) -> Optional[RuleIn]:
        for r in self._rules:
            if r.id == rule_id:
                return r
        return None


# Module-level singleton
_engine: Optional[RuleEngine] = None


def get_rule_engine() -> RuleEngine:
    global _engine
    if _engine is None:
        _engine = RuleEngine()
    return _engine
