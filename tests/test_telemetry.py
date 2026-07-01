"""Tests for the OpenTelemetry integration."""

from opentelemetry.metrics import CallbackOptions

from cronjob_scheduler import telemetry
from cronjob_scheduler.telemetry import (
    cronjob_duration,
    cronjob_executions,
    init_telemetry,
    record_last_run,
    shutdown_telemetry,
)


def _observe() -> dict[str, int]:
    """Run the gauge callback and return {job_id: value}."""
    result: dict[str, int] = {}
    for obs in telemetry._observe_last_run(CallbackOptions()):
        job_id = (obs.attributes or {})["cronjob.job_id"]
        assert isinstance(job_id, str)
        result[job_id] = int(obs.value)
    return result


def test_init_telemetry_disabled_without_endpoint(monkeypatch):
    """Telemetry stays a no-op when no OTLP endpoint is configured."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    assert init_telemetry() is False


def test_init_telemetry_disabled_via_flag(monkeypatch):
    """OTEL_SDK_DISABLED=true forces telemetry off even with an endpoint set."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    assert init_telemetry() is False


def test_instruments_are_safe_to_record_when_disabled():
    """Recording on the instruments never raises, even with no provider installed."""
    cronjob_executions.add(1, {"cronjob.status": "success"})
    cronjob_duration.record(0.5, {"cronjob.status": "success"})
    record_last_run("job", "container", "success")


def test_last_run_gauge_holds_status_until_next_run(monkeypatch):
    """The gauge reports 1 for a failed job and only clears once that job succeeds again."""
    monkeypatch.setattr(telemetry, "_last_run_state", {})

    record_last_run("job-a", "c1", "failure")
    record_last_run("job-b", "c1", "success")
    observed = _observe()
    assert observed == {"job-a": 1, "job-b": 0}

    # A later success on the same job — and only that — clears its failed state.
    record_last_run("job-a", "c1", "success")
    assert _observe()["job-a"] == 0


def test_last_run_gauge_treats_every_non_success_as_failed(monkeypatch):
    """failure, timeout and error all map to 1; only success maps to 0."""
    monkeypatch.setattr(telemetry, "_last_run_state", {})

    for status in ("failure", "timeout", "error"):
        record_last_run("job", "c1", status)
        assert _observe()["job"] == 1, status

    record_last_run("job", "c1", "success")
    assert _observe()["job"] == 0


def test_shutdown_is_safe_without_init():
    """shutdown_telemetry is a no-op when telemetry was never initialised."""
    shutdown_telemetry()


def test_build_resource_defaults_service_name(monkeypatch):
    """A default service.name is set only when the environment does not provide one."""
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)

    resource = telemetry._build_resource()
    assert resource.attributes["service.name"] == "cronjob-scheduler"


def test_build_resource_respects_env_service_name(monkeypatch):
    """An explicit OTEL_SERVICE_NAME wins over the built-in default."""
    monkeypatch.setenv("OTEL_SERVICE_NAME", "scheduler")
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)

    resource = telemetry._build_resource()
    assert resource.attributes["service.name"] == "scheduler"
