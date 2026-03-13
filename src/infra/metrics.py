"""
Prometheus metrics registry for Intune Device Healer.
"""

from prometheus_client import Counter, Gauge, Histogram, Info, CollectorRegistry

# Use the default registry so /metrics serves everything
registry = CollectorRegistry(auto_describe=True)

# ── Counters ──────────────────────────────────────────────────────────────────
jobs_total = Counter(
    "healer_jobs_total",
    "Total number of remediation jobs created",
    ["rule_id"],
    registry=registry,
)

jobs_success = Counter(
    "healer_jobs_success_total",
    "Total number of successful remediation jobs",
    ["rule_id"],
    registry=registry,
)

jobs_failed = Counter(
    "healer_jobs_failed_total",
    "Total number of failed remediation jobs",
    ["rule_id"],
    registry=registry,
)

webhook_events_total = Counter(
    "healer_webhook_events_total",
    "Total webhook events received",
    ["failure_type"],
    registry=registry,
)

# ── Gauges ────────────────────────────────────────────────────────────────────
healer_up = Gauge(
    "healer_up",
    "1 if the healer service is running",
    registry=registry,
)
healer_up.set(1)

jobs_in_flight = Gauge(
    "healer_jobs_in_flight",
    "Number of remediation jobs currently running",
    registry=registry,
)

# ── Histograms ────────────────────────────────────────────────────────────────
job_duration_seconds = Histogram(
    "healer_job_duration_seconds",
    "Duration of a complete remediation job in seconds",
    ["rule_id"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],
    registry=registry,
)

# ── Info ──────────────────────────────────────────────────────────────────────
service_info = Info(
    "healer_service",
    "Intune Device Healer service metadata",
    registry=registry,
)
service_info.info({"version": "1.0.0", "service": "intune-device-healer"})
