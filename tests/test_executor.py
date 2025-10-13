"""Tests for job executor."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dateutil.rrule import HOURLY, rrule

from cronjob_scheduler.executor import execute_job
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
