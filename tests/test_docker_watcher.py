"""Tests for Docker container watcher."""

from unittest.mock import AsyncMock, MagicMock

import aiodocker.exceptions
import pytest

from cronjob_scheduler.docker_watcher import sync_jobs_from_containers
from cronjob_scheduler.scheduler import Scheduler


@pytest.fixture
def scheduler():
    """Create a scheduler instance."""
    return Scheduler()


@pytest.mark.asyncio
async def test_sync_jobs_from_containers_with_label(scheduler):
    """Test syncing jobs from containers with cronjob label."""
    mock_docker = MagicMock()

    # Mock container object with show() method
    mock_container = AsyncMock()
    mock_container.show = AsyncMock(
        return_value={
            "Id": "container123",
            "Config": {"Labels": {"cronjob": "FREQ=HOURLY => python test.py"}},
        }
    )

    mock_docker.containers.list = AsyncMock(return_value=[mock_container])

    await sync_jobs_from_containers(mock_docker, scheduler)

    # Job should be registered
    assert len(scheduler._jobs) == 1
    job_id = list(scheduler._jobs.keys())[0]
    assert "container123" in job_id
    assert scheduler._jobs[job_id].command == "python test.py"


@pytest.mark.asyncio
async def test_sync_jobs_from_containers_without_label(scheduler):
    """Test syncing ignores containers without cronjob label."""
    mock_docker = MagicMock()

    # Mock container without cronjob label
    mock_container = AsyncMock()
    mock_container.show = AsyncMock(return_value={"Id": "container123", "Config": {"Labels": {}}})

    mock_docker.containers.list = AsyncMock(return_value=[mock_container])

    await sync_jobs_from_containers(mock_docker, scheduler)

    # No jobs should be registered
    assert len(scheduler._jobs) == 0


@pytest.mark.asyncio
async def test_sync_jobs_from_containers_multiple_jobs(scheduler):
    """Test syncing multiple jobs from one container."""
    mock_docker = MagicMock()

    # Mock container with multiple jobs
    mock_container = AsyncMock()
    mock_container.show = AsyncMock(
        return_value={
            "Id": "container123",
            "Config": {
                "Labels": {
                    "cronjob": """FREQ=HOURLY => python test.py
FREQ=DAILY;BYHOUR=2 => python cleanup.py"""
                }
            },
        }
    )

    mock_docker.containers.list = AsyncMock(return_value=[mock_container])

    await sync_jobs_from_containers(mock_docker, scheduler)

    # Two jobs should be registered
    assert len(scheduler._jobs) == 2


@pytest.mark.asyncio
async def test_sync_jobs_removes_old_jobs(scheduler):
    """Test that syncing removes jobs from stopped containers."""
    mock_docker = MagicMock()

    # First sync - add a job
    mock_container1 = AsyncMock()
    mock_container1.show = AsyncMock(
        return_value={
            "Id": "container123",
            "Config": {"Labels": {"cronjob": "FREQ=HOURLY => python test.py"}},
        }
    )

    mock_docker.containers.list = AsyncMock(return_value=[mock_container1])

    await sync_jobs_from_containers(mock_docker, scheduler)
    assert len(scheduler._jobs) == 1

    # Second sync - container is gone
    mock_docker.containers.list = AsyncMock(return_value=[])

    await sync_jobs_from_containers(mock_docker, scheduler)

    # Job should be removed
    assert len(scheduler._jobs) == 0


@pytest.mark.asyncio
async def test_sync_jobs_from_multiple_containers(scheduler):
    """Test syncing jobs from multiple containers."""
    mock_docker = MagicMock()

    # Two containers with jobs
    mock_container1 = AsyncMock()
    mock_container1.show = AsyncMock(
        return_value={
            "Id": "container1",
            "Config": {"Labels": {"cronjob": "FREQ=HOURLY => python test1.py"}},
        }
    )

    mock_container2 = AsyncMock()
    mock_container2.show = AsyncMock(
        return_value={
            "Id": "container2",
            "Config": {"Labels": {"cronjob": "FREQ=DAILY => python test2.py"}},
        }
    )

    mock_docker.containers.list = AsyncMock(return_value=[mock_container1, mock_container2])

    await sync_jobs_from_containers(mock_docker, scheduler)

    # Two jobs should be registered
    assert len(scheduler._jobs) == 2

    # Check both containers are represented
    container_ids = {job.container_id for job in scheduler._jobs.values()}
    assert container_ids == {"container1", "container2"}


@pytest.mark.asyncio
async def test_sync_handles_invalid_label(scheduler):
    """Test that invalid cronjob labels are handled gracefully."""
    mock_docker = MagicMock()

    # Mock container with invalid label
    mock_container = AsyncMock()
    mock_container.show = AsyncMock(
        return_value={
            "Id": "container123",
            "Config": {"Labels": {"cronjob": "invalid format"}},
        }
    )

    mock_docker.containers.list = AsyncMock(return_value=[mock_container])

    # Should not raise, just skip the invalid container
    await sync_jobs_from_containers(mock_docker, scheduler)

    # No jobs should be registered
    assert len(scheduler._jobs) == 0


@pytest.mark.asyncio
async def test_sync_handles_container_disappearing(scheduler, caplog):
    """Test that sync handles containers disappearing during sync gracefully."""
    import logging

    caplog.set_level(logging.DEBUG)

    mock_docker = MagicMock()

    # Create a container that will disappear
    mock_container_disappearing = MagicMock()
    mock_container_disappearing.show = AsyncMock(
        side_effect=aiodocker.exceptions.DockerError(404, {"message": "No such container: xyz123"})
    )

    # Create a normal container that will work
    mock_container_normal = MagicMock()
    mock_container_normal.show = AsyncMock(
        return_value={
            "Id": "container2",
            "Name": "/normal-container",
            "Config": {"Labels": {"cronjob": "FREQ=MINUTELY => echo test"}},
        }
    )

    mock_docker.containers.list = AsyncMock(
        return_value=[mock_container_disappearing, mock_container_normal]
    )

    # Sync jobs
    await sync_jobs_from_containers(mock_docker, scheduler)

    # Should handle the disappeared container gracefully
    assert "Container disappeared during sync" in caplog.text

    # Should still process the normal container
    assert len(scheduler._jobs) == 1
    job = list(scheduler._jobs.values())[0]
    assert job.container_id == "container2"
    assert job.command == "echo test"
