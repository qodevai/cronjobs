"""Tests for formatting utilities."""

from datetime import UTC, datetime, timedelta

from dateutil.rrule import HOURLY, rrule

from cronjob_scheduler.formatting import (
    _format_relative_time,
    _truncate,
    format_next_execution,
    format_schedule_table,
)
from cronjob_scheduler.models import ANCHOR, Job


def test_truncate_short_text():
    """Test truncate with text shorter than max length."""
    assert _truncate("hello", 10) == "hello"


def test_truncate_long_text():
    """Test truncate with text longer than max length."""
    assert _truncate("hello world this is long", 10) == "hello w..."


def test_truncate_exact_length():
    """Test truncate with text exactly at max length."""
    assert _truncate("exactly10!", 10) == "exactly10!"


def test_format_relative_time_seconds():
    """Test format relative time for seconds only."""
    assert _format_relative_time(45) == "in 45s"


def test_format_relative_time_minutes():
    """Test format relative time for minutes and seconds."""
    assert _format_relative_time(195) == "in 3m 15s"


def test_format_relative_time_hours():
    """Test format relative time for hours and minutes."""
    assert _format_relative_time(7515) == "in 2h 5m"


def test_format_relative_time_days():
    """Test format relative time for days and hours."""
    assert _format_relative_time(90000) == "in 1d 1h"


def test_format_relative_time_overdue():
    """Test format relative time for negative values (overdue)."""
    assert _format_relative_time(-10) == "overdue"


def test_format_relative_time_zero():
    """Test format relative time for zero seconds."""
    assert _format_relative_time(0) == "in 0s"


def test_format_schedule_table_empty():
    """Test format schedule table with no jobs."""
    result = format_schedule_table({})
    assert result == "Active Schedule: No jobs scheduled"


def test_format_schedule_table_single_job():
    """Test format schedule table with one job."""
    rule = rrule(HOURLY, dtstart=ANCHOR)
    job = Job(
        id="test-job-0",
        container_id="abc123",
        container_name="test-container",
        rrule=rule,
        command="python test.py",
        next_run=datetime(2025, 1, 13, 10, 0, 0, tzinfo=UTC),
    )

    result = format_schedule_table({"test-job-0": job})

    assert "Active Schedule (1 jobs):" in result
    assert "test-container" in result
    assert "python test.py" in result
    assert "2025-01-13 10:00:00" in result
    assert "┌" in result  # Has top border
    assert "└" in result  # Has bottom border
    assert "│" in result  # Has column separators


def test_format_schedule_table_multiple_jobs():
    """Test format schedule table with multiple jobs."""
    rule = rrule(HOURLY, dtstart=ANCHOR)
    job1 = Job(
        id="job-1",
        container_id="abc123",
        container_name="container1",
        rrule=rule,
        command="cmd1",
        next_run=datetime(2025, 1, 13, 10, 0, 0, tzinfo=UTC),
    )
    job2 = Job(
        id="job-2",
        container_id="def456",
        container_name="container2",
        rrule=rule,
        command="cmd2",
        next_run=datetime(2025, 1, 13, 11, 0, 0, tzinfo=UTC),
    )

    result = format_schedule_table({"job-1": job1, "job-2": job2})

    assert "Active Schedule (2 jobs):" in result
    assert "container1" in result
    assert "container2" in result
    assert "cmd1" in result
    assert "cmd2" in result


def test_format_schedule_table_truncates_long_values():
    """Test that format schedule table truncates long values."""
    rule = rrule(HOURLY, dtstart=ANCHOR)
    job = Job(
        id="test-job",
        container_id="abc123",
        container_name="very-very-very-long-container-name-that-exceeds-limit",
        rrule=rule,
        command="python /some/very/very/long/path/to/script.py",
        next_run=datetime(2025, 1, 13, 10, 0, 0, tzinfo=UTC),
    )

    result = format_schedule_table({"test-job": job})

    # Should contain ellipsis for truncated values
    assert "..." in result


def test_format_next_execution_no_jobs():
    """Test format next execution with no jobs."""
    assert format_next_execution({}) is None


def test_format_next_execution_single_job():
    """Test format next execution with one job."""
    rule = rrule(HOURLY, dtstart=ANCHOR)
    future_time = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=5)
    job = Job(
        id="test-job",
        container_id="abc123",
        container_name="test",
        rrule=rule,
        command="test",
        next_run=future_time,
    )

    result = format_next_execution({"test-job": job})

    assert result is not None
    assert "Next job execution:" in result
    assert "(in" in result  # Contains relative time


def test_format_next_execution_multiple_jobs_picks_earliest():
    """Test that format next execution picks the earliest job."""
    rule = rrule(HOURLY, dtstart=ANCHOR)
    now = datetime.now(UTC).replace(microsecond=0)
    job1 = Job(
        id="job-1",
        container_id="abc",
        container_name="test1",
        rrule=rule,
        command="test",
        next_run=now + timedelta(minutes=10),
    )
    job2 = Job(
        id="job-2",
        container_id="def",
        container_name="test2",
        rrule=rule,
        command="test",
        next_run=now + timedelta(minutes=5),  # Earlier
    )

    result = format_next_execution({"job-1": job1, "job-2": job2})

    assert result is not None
    # Should reference the earlier job (5 minutes away)
    assert "in 4m" in result or "in 5m" in result  # Allow for timing variance
