"""Data models for cronjob scheduler."""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from dateutil.rrule import rrule as RRule
from dateutil.rrule import rruleset as RRuleSet
from dateutil.rrule import rrulestr

logger = logging.getLogger(__name__)

# Use current date at midnight as anchor to avoid performance issues
# with high-frequency jobs (SECONDLY/MINUTELY) calculating from distant past
ANCHOR = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


# Longest human-readable portion of a command kept in a job id before it is
# truncated and hash-suffixed. Long enough for a realistic `uv run python -m
# package.module` invocation, short enough to stay readable in an alert.
MAX_COMMAND_SLUG = 60


def _command_slug(command: str) -> str:
    """
    Readable, stable rendering of a command for use inside a job id.

    Stability is the point: this is what makes a job's identity survive a
    redeploy, so an alert that is firing when the container is replaced stays
    the SAME series instead of resolving and re-firing under a new name.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", command)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")  # `python -m x` -> `python-m-x`
    if not slug:  # a command of pure punctuation still needs an identity
        return hashlib.sha256(command.encode()).hexdigest()[:12]
    if len(slug) > MAX_COMMAND_SLUG:
        # Keep the readable head, and make the tail unambiguous: two long
        # commands sharing a 60-char prefix must not collapse into one job.
        digest = hashlib.sha256(command.encode()).hexdigest()[:8]
        slug = f"{slug[:MAX_COMMAND_SLUG].rstrip('-')}-{digest}"
    return slug


def _build_job_ids(container_name: str, specs: list[tuple[str, str, str]]) -> list[str]:
    """
    Assign a stable id to each (rrule, command) pair in a container's label.

    Identity is `container_name:command`, deliberately built from WHAT the job
    is rather than where it happens to live:

    - not `container_id`, which is a fresh SHA on every redeploy
    - not the line's index, which shifts when any line above it is added,
      removed, or reordered

    `container_name` keeps its compose replica suffix (`-1`). That suffix is
    the only thing distinguishing two replicas of one service here, and jobs
    are stored in a dict keyed by id — collapsing it would let one replica's
    job silently overwrite the other's.

    Slugging is lossy (punctuation collapses, long commands truncate), so two
    different jobs can land on the same readable base. Whenever that happens
    — same command on several schedules, or genuinely different commands that
    slug alike — every member of that group gets a digest of its own
    command+schedule appended. The digest depends only on the job's own text,
    never on its position, so reordering cannot swap identities. Unambiguous
    bases (the normal case) stay clean and readable.

    Lines identical in both command and schedule are true duplicates; they get
    an occurrence suffix so neither is dropped, and are logged.

    `specs` carries (normalized rrule, raw rrule, command). The digest uses the
    NORMALIZED schedule, so merely re-casing `freq=hourly` to `FREQ=HOURLY`
    does not re-identify a job; messages echo the RAW text so a warning can be
    grepped against the label the operator actually wrote.
    """
    bases = [f"{container_name}:{_command_slug(command)}" for _norm, _raw, command in specs]

    # A base is ambiguous when more than one DISTINCT (command, schedule) pair
    # resolves to it. Counting distinct pairs, not lines, keeps a genuinely
    # duplicated line from making its base look ambiguous.
    distinct_by_base: dict[str, set[tuple[str, str]]] = {}
    for base, (norm_rrule, _raw, command) in zip(bases, specs, strict=True):
        distinct_by_base.setdefault(base, set()).add((command, norm_rrule))

    ids: list[str] = []
    used: dict[str, int] = {}
    for base, (norm_rrule, raw_rrule, command) in zip(bases, specs, strict=True):
        job_id = base
        if len(distinct_by_base[base]) > 1:
            digest = hashlib.sha256(f"{command}\x00{norm_rrule}".encode()).hexdigest()[:8]
            job_id = f"{base}@{digest}"

        seen = used.get(job_id, 0)
        used[job_id] = seen + 1
        if seen:
            logger.warning(
                "Duplicate cronjob entry in %s (same command and schedule): %s => %s "
                "— disambiguating as #%d; remove the duplicate line if unintended",
                container_name,
                raw_rrule,
                command,
                seen + 1,
            )
            job_id = f"{job_id}#{seen + 1}"
        ids.append(job_id)
    return ids


@dataclass
class Job:
    """Represents a scheduled job."""

    id: str
    container_id: str
    container_name: str
    rrule: RRule | RRuleSet
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
    # (normalized rrule, raw rrule, command, parsed rule)
    parsed: list[tuple[str, str, str, RRule | RRuleSet]] = []
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

        parsed.append((rrule_str_normalized, rrule_str, command, rule))

    # Ids are assigned in a second pass because disambiguating duplicate
    # commands requires knowing the whole label — and doing it per-line would
    # reintroduce exactly the positional dependence this replaces.
    job_ids = _build_job_ids(
        container_name, [(norm, raw, command) for norm, raw, command, _rule in parsed]
    )

    for job_id, (_norm, rrule_str, command, rule) in zip(job_ids, parsed, strict=True):
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
