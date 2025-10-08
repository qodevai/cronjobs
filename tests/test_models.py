"""Tests for models and label parsing."""

from datetime import UTC, datetime

import pytest

from cronjob_scheduler.models import Job, parse_cronjob_label


def test_parse_single_job():
    """Test parsing a single job from label."""
    label = "FREQ=HOURLY => python test.py"
    jobs = parse_cronjob_label(label, container_id="container123")

    assert len(jobs) == 1
    assert jobs[0].container_id == "container123"
    assert jobs[0].command == "python test.py"
    assert jobs[0].rrule is not None


def test_parse_multiple_jobs():
    """Test parsing multiple jobs from multi-line label."""
    label = """FREQ=HOURLY => python test.py
FREQ=DAILY;BYHOUR=2;BYMINUTE=0 => python cleanup.py
FREQ=WEEKLY;BYDAY=MO => python report.py"""

    jobs = parse_cronjob_label(label, container_id="container123")

    assert len(jobs) == 3
    assert jobs[0].command == "python test.py"
    assert jobs[1].command == "python cleanup.py"
    assert jobs[2].command == "python report.py"


def test_parse_job_with_whitespace():
    """Test parsing handles extra whitespace."""
    label = "  FREQ=HOURLY  =>  python test.py  "
    jobs = parse_cronjob_label(label, container_id="container123")

    assert len(jobs) == 1
    assert jobs[0].command == "python test.py"


def test_parse_empty_label():
    """Test parsing empty label returns empty list."""
    assert parse_cronjob_label("", container_id="container123") == []
    assert parse_cronjob_label("   ", container_id="container123") == []


def test_parse_invalid_format():
    """Test parsing invalid format raises error."""
    with pytest.raises(ValueError):
        parse_cronjob_label("FREQ=HOURLY", container_id="container123")

    with pytest.raises(ValueError):
        parse_cronjob_label("python test.py", container_id="container123")


def test_job_id_is_unique():
    """Test each job gets a unique ID."""
    label = """FREQ=HOURLY => python test.py
FREQ=DAILY => python cleanup.py"""

    jobs = parse_cronjob_label(label, container_id="container123")

    assert jobs[0].id != jobs[1].id
    assert "container123" in jobs[0].id
    assert "container123" in jobs[1].id


def test_job_dataclass():
    """Test Job dataclass structure."""
    from dateutil.rrule import HOURLY, rrule

    rule = rrule(HOURLY, dtstart=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC))
    job = Job(
        id="test-123",
        container_id="container123",
        rrule=rule,
        command="python test.py",
        next_run=datetime(2025, 1, 1, 1, 0, 0, tzinfo=UTC),
    )

    assert job.id == "test-123"
    assert job.container_id == "container123"
    assert job.command == "python test.py"
    assert job.next_run.hour == 1


def test_parse_lowercase_rrule():
    """Test parsing lowercase RRULE (should be normalized)."""
    label = "freq=minutely;interval=5 => python test.py"
    jobs = parse_cronjob_label(label, container_id="container123")

    assert len(jobs) == 1
    assert jobs[0].command == "python test.py"
    assert jobs[0].rrule is not None


def test_parse_mixed_case_rrule():
    """Test parsing mixed-case RRULE (should be normalized)."""
    label = "Freq=Hourly => python test.py"
    jobs = parse_cronjob_label(label, container_id="container123")

    assert len(jobs) == 1
    assert jobs[0].command == "python test.py"
    assert jobs[0].rrule is not None


def test_parse_lowercase_with_params():
    """Test parsing lowercase RRULE with parameters."""
    label = "freq=daily;byhour=2;byminute=30 => python cleanup.py"
    jobs = parse_cronjob_label(label, container_id="container123")

    assert len(jobs) == 1
    assert jobs[0].command == "python cleanup.py"
    assert jobs[0].rrule is not None
