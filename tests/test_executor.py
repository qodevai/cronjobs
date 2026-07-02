"""Tests for job executor."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dateutil.rrule import HOURLY, rrule

from cronjob_scheduler.executor import FAILURE_OUTPUT_CHARS, _tail, execute_job
from cronjob_scheduler.models import ANCHOR, Job


def create_test_job(job_id: str = "job1", command: str = "echo test") -> Job:
    """Helper to create a test job."""
    rule = rrule(HOURLY, dtstart=ANCHOR)
    return Job(
        id=job_id,
        container_id="container123",
        container_name="test-container",
        rrule=rule,
        command=command,
        next_run=ANCHOR,
    )


@pytest.mark.asyncio
async def test_execute_job_success(mocker):
    """Test successful job execution."""
    # Mock docker client
    mock_docker = MagicMock()
    mock_container = AsyncMock()
    mock_docker.containers.get = AsyncMock(return_value=mock_container)

    # Mock exec result with streaming output
    mock_msg = MagicMock()
    mock_msg.data = b"test output\n"

    mock_stream = AsyncMock()
    mock_stream.read_out = AsyncMock(side_effect=[mock_msg, None])

    mock_exec = AsyncMock()
    mock_exec.start = MagicMock(return_value=mock_stream)
    mock_exec.inspect = AsyncMock(return_value={"ExitCode": 0})
    mock_container.exec = AsyncMock(return_value=mock_exec)

    job = create_test_job(command="python test.py")

    exit_code = await execute_job(mock_docker, job)

    # Verify container.exec was called with correct command
    mock_docker.containers.get.assert_called_once_with("container123")
    mock_container.exec.assert_called_once()

    # Check the command was passed correctly
    call_args = mock_container.exec.call_args
    assert "python test.py" in str(call_args)

    assert exit_code == 0


@pytest.mark.asyncio
async def test_execute_job_failure(mocker):
    """Test job execution with non-zero exit code."""
    mock_docker = MagicMock()
    mock_container = AsyncMock()
    mock_docker.containers.get = AsyncMock(return_value=mock_container)

    # Mock exec result with failure
    mock_msg = MagicMock()
    mock_msg.data = b"error output\n"

    mock_stream = AsyncMock()
    mock_stream.read_out = AsyncMock(side_effect=[mock_msg, None])

    mock_exec = AsyncMock()
    mock_exec.start = MagicMock(return_value=mock_stream)
    mock_exec.inspect = AsyncMock(return_value={"ExitCode": 1})
    mock_container.exec = AsyncMock(return_value=mock_exec)

    job = create_test_job()

    exit_code = await execute_job(mock_docker, job)

    assert exit_code == 1


@pytest.mark.asyncio
async def test_execute_job_container_not_found(mocker):
    """Test execution when container doesn't exist."""
    mock_docker = MagicMock()

    # Simulate container not found
    from aiodocker.exceptions import DockerError

    mock_docker.containers.get = AsyncMock(
        side_effect=DockerError(status=404, data={"message": "No such container"})
    )

    job = create_test_job()

    exit_code = await execute_job(mock_docker, job)

    # Should return -1 or some error code
    assert exit_code == -1


@pytest.mark.asyncio
async def test_execute_job_exec_error(mocker):
    """Test execution when exec command fails."""
    mock_docker = MagicMock()
    mock_container = AsyncMock()
    mock_docker.containers.get = AsyncMock(return_value=mock_container)

    # Simulate exec error
    mock_container.exec = AsyncMock(side_effect=Exception("Exec failed"))

    job = create_test_job()

    exit_code = await execute_job(mock_docker, job)

    assert exit_code == -1


@pytest.mark.asyncio
async def test_execute_job_with_complex_command(mocker):
    """Test execution with complex shell command."""
    mock_docker = MagicMock()
    mock_container = AsyncMock()
    mock_docker.containers.get = AsyncMock(return_value=mock_container)

    mock_msg1 = MagicMock()
    mock_msg1.data = b"hello\n"
    mock_msg2 = MagicMock()
    mock_msg2.data = b"world\n"

    mock_stream = AsyncMock()
    mock_stream.read_out = AsyncMock(side_effect=[mock_msg1, mock_msg2, None])

    mock_exec = AsyncMock()
    mock_exec.start = MagicMock(return_value=mock_stream)
    mock_exec.inspect = AsyncMock(return_value={"ExitCode": 0})
    mock_container.exec = AsyncMock(return_value=mock_exec)

    job = create_test_job(command="bash -c 'echo hello && echo world'")

    exit_code = await execute_job(mock_docker, job)

    assert exit_code == 0
    mock_container.exec.assert_called_once()


def _make_recording_exec(exit_code: int = 0):
    """Build mocked docker/container/exec objects for a single execution."""
    mock_docker = MagicMock()
    mock_container = AsyncMock()
    mock_docker.containers.get = AsyncMock(return_value=mock_container)

    mock_msg = MagicMock()
    mock_msg.data = b"output\n"
    mock_stream = AsyncMock()
    mock_stream.read_out = AsyncMock(side_effect=[mock_msg, None])

    mock_exec = AsyncMock()
    mock_exec.start = MagicMock(return_value=mock_stream)
    mock_exec.inspect = AsyncMock(return_value={"ExitCode": exit_code})
    mock_container.exec = AsyncMock(return_value=mock_exec)
    return mock_docker, mock_container


@pytest.mark.asyncio
async def test_execute_job_injects_trace_context_into_exec_env(monkeypatch):
    """With an active recording span, the W3C trace context is passed to the exec env."""
    from opentelemetry.sdk.trace import TracerProvider

    import cronjob_scheduler.executor as executor_mod

    # Give the executor a real (recording) tracer so context injection produces a
    # traceparent. The executor imports `tracer` by value, so patch its own binding.
    provider = TracerProvider()
    monkeypatch.setattr(executor_mod, "tracer", provider.get_tracer("test"))

    mock_docker, mock_container = _make_recording_exec(exit_code=0)
    job = create_test_job(command="python sync.py")

    exit_code = await execute_job(mock_docker, job)

    assert exit_code == 0
    environment = mock_container.exec.call_args.kwargs["environment"]
    assert environment is not None
    assert "TRACEPARENT" in environment
    # W3C traceparent format: version-traceid-spanid-flags
    assert environment["TRACEPARENT"].count("-") == 3


@pytest.mark.asyncio
async def test_execute_job_no_trace_context_when_disabled(monkeypatch):
    """With telemetry disabled (no-op tracer), no trace env vars are injected."""
    from opentelemetry import trace

    import cronjob_scheduler.executor as executor_mod

    monkeypatch.setattr(executor_mod, "tracer", trace.get_tracer("noop"))

    mock_docker, mock_container = _make_recording_exec(exit_code=0)
    job = create_test_job(command="python sync.py")

    await execute_job(mock_docker, job)

    # No recording span -> empty carrier -> environment passed as None
    assert mock_container.exec.call_args.kwargs["environment"] is None


def test_tail_keeps_end_and_marks_truncation():
    """_tail returns the end of the text (where errors are) and flags truncation."""
    assert _tail("short output", 100) == "short output"

    long = "HEAD_NOISE" + "x" * (FAILURE_OUTPUT_CHARS + 500) + "TRACEBACK_END"
    out = _tail(long, FAILURE_OUTPUT_CHARS)
    assert "TRACEBACK_END" in out  # the tail (error) is kept
    assert "HEAD_NOISE" not in out  # the head (startup noise) is dropped
    assert out.startswith("…[truncated")


@pytest.mark.asyncio
async def test_execute_job_failure_logs_output_tail(caplog):
    """A failed job logs the tail of its output — the error — not just the head."""
    mock_docker = MagicMock()
    mock_container = AsyncMock()
    mock_docker.containers.get = AsyncMock(return_value=mock_container)

    # >200 chars of startup noise (what the old head-truncation showed), then the error.
    head = "INFO connecting to postgres...\n" * 40
    mock_msg = MagicMock()
    mock_msg.data = (head + "Traceback (most recent call last):\nRuntimeError: boom\n").encode()
    mock_stream = AsyncMock()
    mock_stream.read_out = AsyncMock(side_effect=[mock_msg, None])

    mock_exec = AsyncMock()
    mock_exec.start = MagicMock(return_value=mock_stream)
    mock_exec.inspect = AsyncMock(return_value={"ExitCode": 1})
    mock_container.exec = AsyncMock(return_value=mock_exec)

    with caplog.at_level("WARNING"):
        exit_code = await execute_job(mock_docker, create_test_job())

    assert exit_code == 1
    assert "RuntimeError: boom" in caplog.text  # the real error is now visible in the log
