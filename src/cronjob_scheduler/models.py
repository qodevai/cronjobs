"""Data models for cronjob scheduler."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from dateutil.rrule import rrulestr

logger = logging.getLogger(__name__)

# Use current date at midnight as anchor to avoid performance issues
# with high-frequency jobs (SECONDLY/MINUTELY) calculating from distant past
ANCHOR = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass
class Job:
    """Represents a scheduled job."""

    id: str
    container_id: str
    container_name: str
    rrule: any  # dateutil.rrule.rrule instance
    command: str
    next_run: datetime


def parse_cronjob_label(label: str, container_id: str, container_name: str) -> list[Job]:
    """
    Parse cronjob label into Job objects.

    Format: FREQ=... => command
    Multiple jobs separated by newlines.

    Args:
        label: The cronjob label value
        container_id: Container ID this job belongs to
        container_name: Container name for display

    Returns:
        List of Job objects

    Raises:
        ValueError: If label format is invalid
    """
    if not label or not label.strip():
        logger.debug("Empty label for container %s", container_id[:12])
        return []

    jobs = []
    lines = label.strip().split("\n")
    logger.debug("Parsing %d line(s) from cronjob label in %s", len(lines), container_id[:12])

    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        if "=>" not in line:
            logger.error("Missing '=>' separator in line %d: %s", idx, line)
            raise ValueError(f"Invalid job format: missing '=>' separator in '{line}'")

        parts = line.split("=>", 1)
        if len(parts) != 2:
            logger.error("Invalid format in line %d: %s", idx, line)
            raise ValueError(f"Invalid job format: '{line}'")

        rrule_str = parts[0].strip()
        command = parts[1].strip()

        if not rrule_str or not command:
            logger.error("Empty schedule or command in line %d: %s", idx, line)
            raise ValueError(f"Invalid job format: empty schedule or command in '{line}'")

        # Normalize RRULE to uppercase (dateutil.rrule expects uppercase)
        rrule_str_normalized = rrule_str.upper()
        logger.debug("Parsing RRULE: %s (normalized: %s)", rrule_str, rrule_str_normalized)

        # Parse RRULE with anchor
        try:
            rule = rrulestr(rrule_str_normalized, dtstart=ANCHOR)
        except Exception as e:
            logger.error("Failed to parse RRULE '%s': %s", rrule_str, e)
            raise ValueError(f"Invalid RRULE '{rrule_str}': {e}") from e

        # Generate unique job ID
        job_id = f"{container_id}-job-{idx}"

        # Create job (next_run will be set by scheduler)
        job = Job(
            id=job_id,
            container_id=container_id,
            container_name=container_name,
            rrule=rule,
            command=command,
            next_run=ANCHOR,  # Placeholder, scheduler will set this
        )
        logger.debug("Created job %s: %s => %s", job_id, rrule_str, command)
        jobs.append(job)

    logger.debug("Successfully parsed %d job(s) from container %s", len(jobs), container_id[:12])
    return jobs
