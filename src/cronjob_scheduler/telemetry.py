"""
OpenTelemetry integration for metrics and traces.

Telemetry is **opt-in and vendor-neutral**: it is configured entirely through the
standard ``OTEL_*`` environment variables and stays a no-op unless an OTLP endpoint
is provided. No specific backend is assumed.

What it emits when enabled:

- Metrics
    - ``cronjob.executions`` (counter): one increment per job run, tagged with
      ``cronjob.status`` (``success`` | ``failure`` | ``timeout`` | ``error``).
    - ``cronjob.duration`` (histogram, seconds): wall-clock time of each run.
    - ``cronjob.last_run_failed`` (observable gauge): ``1`` when a job's most recent run
      did not succeed, else ``0``. Held between runs, so it reflects *current* state and
      only clears when the same job runs again and succeeds — unlike the windowed counter.
- Traces
    - One ``cronjob.execute`` span per run. The span's W3C trace context is injected
      into the executed command's environment (``TRACEPARENT`` / ``TRACESTATE``) so an
      instrumented job can continue the same trace. See ``executor.py``.

Enable it by setting ``OTEL_EXPORTER_OTLP_ENDPOINT`` (and usually
``OTEL_EXPORTER_OTLP_HEADERS`` and ``OTEL_RESOURCE_ATTRIBUTES``). Set
``OTEL_SDK_DISABLED=true`` to force it off even when an endpoint is configured.
"""

import logging
import os
import threading

from opentelemetry import metrics, trace
from opentelemetry.metrics import CallbackOptions, Observation

logger = logging.getLogger(__name__)

# Instruments are created against the global providers. Before init_telemetry() installs
# real providers these resolve to no-op proxies, so recording is always safe to call.
_meter = metrics.get_meter("cronjob_scheduler")
tracer = trace.get_tracer("cronjob_scheduler")

cronjob_executions = _meter.create_counter(
    "cronjob.executions",
    unit="1",
    description="Number of cronjob executions, tagged by terminal status.",
)
cronjob_duration = _meter.create_histogram(
    "cronjob.duration",
    unit="s",
    description="Wall-clock duration of a cronjob execution in seconds.",
)

# Per-job "most recent run" state backing the cronjob.last_run_failed observable gauge.
# Keyed by (job_id, container_name); the value is (failed, attributes) where ``failed`` is
# 1 when the last run did not succeed, else 0. A lock guards it because the executor
# (asyncio thread) writes while the metric reader's background thread reads it in the
# gauge callback.
_last_run_lock = threading.Lock()
_last_run_state: dict[tuple[str, str], tuple[int, dict[str, str]]] = {}


def record_last_run(job_id: str, container_name: str, status: str) -> None:
    """
    Record the terminal status of a job's most recent run for ``cronjob.last_run_failed``.

    ``failed`` is 0 when ``status`` is ``success`` and 1 for every non-success terminal
    status (``failure`` / ``timeout`` / ``error``). The value is retained until the *same*
    job runs again, so an alert on the gauge stays firing after a failure and clears only
    once a later run of that job succeeds — a windowed counter, by contrast, forgets a
    failure as soon as it ages out of the evaluation window.
    """
    failed = 0 if status == "success" else 1
    attributes = {
        "cronjob.job_id": job_id,
        "cronjob.container_name": container_name,
    }
    with _last_run_lock:
        _last_run_state[(job_id, container_name)] = (failed, attributes)


def _observe_last_run(options: CallbackOptions) -> list[Observation]:
    """Emit the last-known status for every job seen so far (held between runs)."""
    with _last_run_lock:
        snapshot = list(_last_run_state.values())
    return [Observation(failed, attributes) for failed, attributes in snapshot]


cronjob_last_run_failed = _meter.create_observable_gauge(
    "cronjob.last_run_failed",
    callbacks=[_observe_last_run],
    unit="1",
    description=(
        "1 if a job's most recent run did not succeed, else 0; held until the job runs "
        "again so it reflects current state rather than a windowed count."
    ),
)

# Providers are kept module-global so shutdown_telemetry() can flush them on exit.
_meter_provider = None
_tracer_provider = None


def _telemetry_endpoint() -> str | None:
    """Return the configured OTLP endpoint, or None if telemetry is unconfigured."""
    return (
        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    )


def _build_resource():
    """
    Build the OTel Resource, defaulting service.name only if the env does not set it.

    The standard ``OTEL_SERVICE_NAME`` / ``OTEL_RESOURCE_ATTRIBUTES`` variables always win;
    the default is just a friendly fallback so unconfigured deployments are still labelled.
    """
    from opentelemetry.sdk.resources import Resource

    attributes = {}
    env_attrs = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
    if not os.getenv("OTEL_SERVICE_NAME") and "service.name" not in env_attrs:
        attributes["service.name"] = "cronjob-scheduler"
    return Resource.create(attributes)


def init_telemetry() -> bool:
    """
    Initialise OpenTelemetry metrics and traces from environment configuration.

    Returns:
        True if telemetry was enabled, False if it stayed a no-op (not configured or
        explicitly disabled).
    """
    global _meter_provider, _tracer_provider

    if os.getenv("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        logger.info("OpenTelemetry disabled via OTEL_SDK_DISABLED")
        return False

    endpoint = _telemetry_endpoint()
    if not endpoint:
        logger.debug(
            "OpenTelemetry not configured (no OTEL_EXPORTER_OTLP_ENDPOINT); "
            "metrics and traces are disabled"
        )
        return False

    # Imported lazily so the SDK is only pulled in when telemetry is actually used.
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = _build_resource()

    # Exporters read OTEL_EXPORTER_OTLP_ENDPOINT / _HEADERS / _PROTOCOL from the environment
    # and append the /v1/metrics and /v1/traces paths to the base endpoint themselves.
    _meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(_meter_provider)

    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(_tracer_provider)

    logger.info("OpenTelemetry initialised (OTLP endpoint: %s)", endpoint)
    return True


def shutdown_telemetry() -> None:
    """Flush and shut down telemetry providers so buffered data is exported on exit."""
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
    if _meter_provider is not None:
        _meter_provider.shutdown()
