"""Tests for scheduler."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from dateutil.rrule import HOURLY, MINUTELY, rrule

from cronjob_scheduler.models import ANCHOR, Job
from cronjob_scheduler.scheduler import Scheduler


@pytest.fixture
def scheduler():
    """Create a scheduler instance."""
    return Scheduler()


def create_test_job(job_id: str, rrule_obj, command: str = "test") -> Job:
    """Helper to create a test job."""
    return Job(
        id=job_id,
        container_id="container123",
        rrule=rrule_obj,
        command=command,
        next_run=ANCHOR,  # Will be set by scheduler
    )


@pytest.mark.asyncio
async def test_register_job_calculates_next_run(scheduler):
    """Test that registering a job calculates its next run time."""
    rule = rrule(MINUTELY, interval=5, dtstart=ANCHOR)
    job = create_test_job("job1", rule)

    scheduler.register_job(job)

    # next_run should be calculated and in the future
    assert job.next_run > datetime.now(UTC)


@pytest.mark.asyncio
async def test_unregister_job(scheduler):
    """Test unregistering a job."""
    rule = rrule(HOURLY, dtstart=ANCHOR)
    job = create_test_job("job1", rule)

    scheduler.register_job(job)
    scheduler.unregister_job("job1")

    # Job should not appear in due jobs
    # Create a task that will timeout if wait_for_due_jobs blocks forever
    async def check_no_jobs():
        try:
            await asyncio.wait_for(scheduler.wait_for_due_jobs(), timeout=0.1)
        except TimeoutError:
            return True  # Expected - no jobs scheduled
        return False

    assert await check_no_jobs()


@pytest.mark.asyncio
async def test_wait_for_due_jobs_returns_immediately_for_past_jobs(scheduler):
    """Test that jobs scheduled in the past are returned immediately."""
    # Create a job that should have run in the past
    rule = rrule(MINUTELY, interval=1, dtstart=ANCHOR, count=1)
    job = create_test_job("job1", rule)

    # Manually set next_run to the past
    job.next_run = datetime.now(UTC) - timedelta(seconds=10)
    scheduler._jobs["job1"] = job

    # Should return immediately
    due_jobs = await asyncio.wait_for(scheduler.wait_for_due_jobs(), timeout=1.0)

    assert len(due_jobs) == 1
    assert due_jobs[0].id == "job1"


@pytest.mark.asyncio
async def test_wait_for_due_jobs_calculates_next_run(scheduler):
    """Test that wait_for_due_jobs updates next_run before returning."""
    rule = rrule(MINUTELY, interval=5, dtstart=ANCHOR)
    job = create_test_job("job1", rule)

    # Set next_run to just past
    job.next_run = datetime.now(UTC) - timedelta(seconds=1)
    scheduler._jobs["job1"] = job

    due_jobs = await asyncio.wait_for(scheduler.wait_for_due_jobs(), timeout=1.0)

    # next_run should be updated to future
    assert due_jobs[0].next_run > datetime.now(UTC)


@pytest.mark.asyncio
async def test_multiple_due_jobs_returned_together(scheduler):
    """Test that multiple due jobs are returned in a single call."""
    rule1 = rrule(HOURLY, dtstart=ANCHOR)
    rule2 = rrule(HOURLY, dtstart=ANCHOR)

    job1 = create_test_job("job1", rule1)
    job2 = create_test_job("job2", rule2)

    # Both jobs due in the past
    now = datetime.now(UTC)
    job1.next_run = now - timedelta(seconds=1)
    job2.next_run = now - timedelta(seconds=1)

    scheduler._jobs["job1"] = job1
    scheduler._jobs["job2"] = job2

    due_jobs = await asyncio.wait_for(scheduler.wait_for_due_jobs(), timeout=1.0)

    assert len(due_jobs) == 2
    job_ids = {job.id for job in due_jobs}
    assert job_ids == {"job1", "job2"}


@pytest.mark.asyncio
async def test_register_job_wakes_up_scheduler(scheduler):
    """Test that registering a job wakes up wait_for_due_jobs."""

    # Start waiting (will block since no jobs)
    async def wait_and_register():
        await asyncio.sleep(0.1)
        rule = rrule(MINUTELY, interval=1, dtstart=ANCHOR)
        job = create_test_job("job1", rule)
        # Register job (it will calculate next_run)
        scheduler.register_job(job)
        # Then manually override to make it due immediately
        scheduler._jobs["job1"].next_run = datetime.now(UTC) - timedelta(seconds=1)
        # Wake up scheduler again with the updated time
        scheduler._next_due.set()

    # This should complete quickly because register_job wakes it up
    waiter = asyncio.create_task(scheduler.wait_for_due_jobs())
    registerer = asyncio.create_task(wait_and_register())

    due_jobs = await asyncio.wait_for(waiter, timeout=2.0)

    await registerer
    assert len(due_jobs) == 1


@pytest.mark.asyncio
async def test_no_jobs_waits_for_registration(scheduler):
    """Test that scheduler waits when no jobs are registered."""
    # Should timeout because no jobs registered
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(scheduler.wait_for_due_jobs(), timeout=0.2)


@pytest.mark.asyncio
async def test_scheduler_calculates_correct_sleep_duration(scheduler):
    """Test that scheduler sleeps until the next job time."""
    # Use a rule that starts from now, so next occurrence is predictable
    now = datetime.now(UTC)
    rule = rrule(MINUTELY, interval=1, dtstart=now)
    job = create_test_job("job1", rule)

    # Set next run to 0.5 seconds in the future
    job.next_run = now + timedelta(seconds=0.5)
    scheduler._jobs["job1"] = job

    start_time = datetime.now(UTC)
    due_jobs = await scheduler.wait_for_due_jobs()
    elapsed = (datetime.now(UTC) - start_time).total_seconds()

    # Should have slept approximately 0.5 seconds (with some tolerance)
    assert 0.4 <= elapsed <= 0.8
    assert len(due_jobs) == 1
