"""Tests for models and label parsing."""

import logging
from datetime import UTC, datetime

import pytest

from cronjob_scheduler.models import Job, parse_cronjob_label


def test_parse_single_job():
    """Test parsing a single job from label."""
    label = "FREQ=HOURLY => python test.py"
    jobs = parse_cronjob_label(label, container_id="container123", container_name="test-container")

    assert len(jobs) == 1
    assert jobs[0].container_id == "container123"
    assert jobs[0].command == "python test.py"
    assert jobs[0].rrule is not None


def test_parse_multiple_jobs():
    """Test parsing multiple jobs from multi-line label."""
    label = """FREQ=HOURLY => python test.py
FREQ=DAILY;BYHOUR=2;BYMINUTE=0 => python cleanup.py
FREQ=WEEKLY;BYDAY=MO => python report.py"""

    jobs = parse_cronjob_label(label, container_id="container123", container_name="test-container")

    assert len(jobs) == 3
    assert jobs[0].command == "python test.py"
    assert jobs[1].command == "python cleanup.py"
    assert jobs[2].command == "python report.py"


def test_parse_job_with_whitespace():
    """Test parsing handles extra whitespace."""
    label = "  FREQ=HOURLY  =>  python test.py  "
    jobs = parse_cronjob_label(label, container_id="container123", container_name="test-container")

    assert len(jobs) == 1
    assert jobs[0].command == "python test.py"


def test_parse_empty_label():
    """Test parsing empty label returns empty list."""
    assert (
        parse_cronjob_label("", container_id="container123", container_name="test-container") == []
    )
    assert (
        parse_cronjob_label("   ", container_id="container123", container_name="test-container")
        == []
    )


def test_parse_invalid_format():
    """Test parsing invalid format raises error."""
    with pytest.raises(ValueError):
        parse_cronjob_label(
            "FREQ=HOURLY", container_id="container123", container_name="test-container"
        )

    with pytest.raises(ValueError):
        parse_cronjob_label(
            "python test.py", container_id="container123", container_name="test-container"
        )


def test_job_id_is_unique():
    """Test each job gets a unique ID."""
    label = """FREQ=HOURLY => python test.py
FREQ=DAILY => python cleanup.py"""

    jobs = parse_cronjob_label(label, container_id="container123", container_name="test-container")

    assert jobs[0].id != jobs[1].id
    # Identity is the container NAME plus the command — deliberately not the
    # container id, which changes on every redeploy.
    assert jobs[0].id == "test-container:python-test.py"
    assert jobs[1].id == "test-container:python-cleanup.py"


class TestStableJobIds:
    """
    Job identity must describe WHAT the job is, not where it happens to live.

    It used to be `f"{container_id}-job-{idx}"`, which moved on two axes: the
    container id is a fresh SHA per redeploy, and the index shifts when any line
    above it changes. Both broke the `cronjob.last_run_failed` series: a job that
    was failing across a redeploy had its alert resolve and re-fire under a new
    name, splitting its history and briefly hiding a real failure.
    """

    LABEL = """FREQ=HOURLY => python sync_outlook_emails.py
FREQ=DAILY;BYHOUR=6 => python sync_apollo_deals.py"""

    def test_id_survives_a_redeploy(self):
        """The core fix: a new container id must not re-identify the same job."""
        before = parse_cronjob_label(self.LABEL, "aaaa1111", "dashboard-1")
        after = parse_cronjob_label(self.LABEL, "bbbb2222", "dashboard-1")

        assert [j.id for j in before] == [j.id for j in after]

    def test_id_survives_reordering(self):
        """
        Swapping two lines must not swap their identities — otherwise a firing
        alert could be resolved by a different job succeeding."""
        reordered = """FREQ=DAILY;BYHOUR=6 => python sync_apollo_deals.py
FREQ=HOURLY => python sync_outlook_emails.py"""

        original = {j.command: j.id for j in parse_cronjob_label(self.LABEL, "c1", "dash-1")}
        shuffled = {j.command: j.id for j in parse_cronjob_label(reordered, "c1", "dash-1")}

        assert original == shuffled

    def test_id_survives_an_inserted_line(self):
        """Adding a job at the top used to renumber every job below it."""
        with_new = (
            """FREQ=HOURLY;BYMINUTE=5 => python brand_new.py
"""
            + self.LABEL
        )

        original = {j.command: j.id for j in parse_cronjob_label(self.LABEL, "c1", "dash-1")}
        extended = {j.command: j.id for j in parse_cronjob_label(with_new, "c1", "dash-1")}

        for command, job_id in original.items():
            assert extended[command] == job_id

    def test_id_survives_rescheduling(self):
        """
        Moving a job's slot is not a new job. Rescheduling the notes sync from
        :20 to :35 should keep one continuous series, not start a fresh one."""
        before = parse_cronjob_label("FREQ=HOURLY;BYMINUTE=20 => python notes.py", "c1", "dash-1")
        after = parse_cronjob_label("FREQ=HOURLY;BYMINUTE=35 => python notes.py", "c1", "dash-1")

        assert before[0].id == after[0].id

    def test_id_names_the_job(self):
        """
        The practical win: an alert should say what failed. The old ids read
        `584d5ef958...-job-13`, which told an operator nothing."""
        (job,) = parse_cronjob_label(
            "FREQ=HOURLY => python sync_outlook_emails.py", "c1", "linkedin-dashboard-dashboard-1"
        )
        assert job.id == "linkedin-dashboard-dashboard-1:python-sync_outlook_emails.py"

    def test_replicas_stay_distinct(self):
        """
        The compose replica suffix is load-bearing, not decoration: jobs live in
        a dict keyed by id, so collapsing `-1`/`-2` would let one replica's job
        silently overwrite the other's."""
        one = parse_cronjob_label(self.LABEL, "c1", "dash-1")
        two = parse_cronjob_label(self.LABEL, "c2", "dash-2")

        assert {j.id for j in one}.isdisjoint({j.id for j in two})

    def test_same_command_on_two_schedules_is_disambiguated_by_schedule(self):
        """
        ...and by schedule rather than position, so reordering the pair cannot
        swap which series is which."""
        label = """FREQ=DAILY;BYHOUR=6 => python report.py
FREQ=DAILY;BYHOUR=18 => python report.py"""
        flipped = """FREQ=DAILY;BYHOUR=18 => python report.py
FREQ=DAILY;BYHOUR=6 => python report.py"""

        first = parse_cronjob_label(label, "c1", "dash-1")
        second = parse_cronjob_label(flipped, "c1", "dash-1")

        assert first[0].id != first[1].id
        assert first[0].id == second[1].id, "the 06:00 job keeps its identity"
        assert first[1].id == second[0].id, "so does the 18:00 job"

    def test_exact_duplicate_lines_are_kept_and_warned(self, caplog):
        """A genuinely duplicated line must not silently vanish into a dict key."""
        label = """FREQ=HOURLY => python x.py
FREQ=HOURLY => python x.py"""

        with caplog.at_level(logging.WARNING):
            jobs = parse_cronjob_label(label, "c1", "dash-1")

        assert len({j.id for j in jobs}) == 2, "neither line may be dropped"
        assert "Duplicate cronjob entry" in caplog.text

    def test_long_commands_stay_distinct(self):
        """Truncation must not merge two jobs sharing a long prefix."""
        prefix = "uv run python -m app.interfaces.cli.a_very_long_module_path_indeed"
        label = f"""FREQ=HOURLY => {prefix}_alpha
FREQ=HOURLY => {prefix}_beta"""

        jobs = parse_cronjob_label(label, "c1", "dash-1")
        assert jobs[0].id != jobs[1].id

    def test_long_command_id_stays_readable_and_bounded(self):
        command = "uv run python -m " + "a" * 200
        (job,) = parse_cronjob_label(f"FREQ=HOURLY => {command}", "c1", "dash-1")

        assert job.id.startswith("dash-1:uv-run-python-m-")
        assert len(job.id) < 120

    def test_different_commands_that_slug_alike_stay_distinct(self):
        """
        Slugging is lossy — punctuation collapses — so two different commands can
        reach the same readable base. They must not then collide into one dict key."""
        label = """FREQ=HOURLY => python -m x
FREQ=HOURLY => python  -m  x"""

        jobs = parse_cronjob_label(label, "c1", "dash-1")
        assert jobs[0].id != jobs[1].id

    def test_unambiguous_ids_carry_no_digest(self):
        """
        The readable case must stay readable — a digest only appears when the
        base is genuinely ambiguous."""
        jobs = parse_cronjob_label(self.LABEL, "c1", "dash-1")
        assert all("@" not in j.id for j in jobs)

    def test_punctuation_only_command_still_gets_an_id(self):
        (job,) = parse_cronjob_label("FREQ=HOURLY => @@@", "c1", "dash-1")
        assert job.id.startswith("dash-1:")
        assert job.id != "dash-1:"


def test_job_dataclass():
    """Test Job dataclass structure."""
    from dateutil.rrule import HOURLY, rrule

    rule = rrule(HOURLY, dtstart=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC))
    job = Job(
        id="test-123",
        container_id="container123",
        container_name="test-container",
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
    jobs = parse_cronjob_label(label, container_id="container123", container_name="test-container")

    assert len(jobs) == 1
    assert jobs[0].command == "python test.py"
    assert jobs[0].rrule is not None


def test_parse_mixed_case_rrule():
    """Test parsing mixed-case RRULE (should be normalized)."""
    label = "Freq=Hourly => python test.py"
    jobs = parse_cronjob_label(label, container_id="container123", container_name="test-container")

    assert len(jobs) == 1
    assert jobs[0].command == "python test.py"
    assert jobs[0].rrule is not None


def test_parse_lowercase_with_params():
    """Test parsing lowercase RRULE with parameters."""
    label = "freq=daily;byhour=2;byminute=30 => python cleanup.py"
    jobs = parse_cronjob_label(label, container_id="container123", container_name="test-container")

    assert len(jobs) == 1
    assert jobs[0].command == "python cleanup.py"
    assert jobs[0].rrule is not None
