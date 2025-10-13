"""Table formatting utilities for schedule display."""

from datetime import UTC, datetime

from cronjob_scheduler.models import Job

# Column width constants
COL_CONTAINER = 20
COL_SCHEDULE = 30
COL_COMMAND = 30
COL_NEXT_RUN = 19


def _truncate(text: str, max_len: int) -> str:
    """
    Truncate text with ellipsis if exceeds max length.

    Args:
        text: Text to truncate
        max_len: Maximum length including ellipsis

    Returns:
        Truncated text with "..." or original if short enough
    """
    return text[: max_len - 3] + "..." if len(text) > max_len else text


def _format_relative_time(seconds: float) -> str:
    """
    Format seconds as relative time string.

    Args:
        seconds: Number of seconds until event

    Returns:
        Formatted string like "in 4m 45s", "in 2h 15m", "in 1d 3h", or "overdue"
    """
    if seconds < 0:
        return "overdue"

    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if days > 0:
        return f"in {days}d {hours}h"
    if hours > 0:
        return f"in {hours}h {minutes}m"
    if minutes > 0:
        return f"in {minutes}m {secs}s"
    return f"in {secs}s"


def _build_border(top: bool = False, middle: bool = False, _bottom: bool = False) -> str:
    """
    Build table border line with box drawing characters.

    Args:
        top: Build top border
        middle: Build middle separator
        _bottom: Build bottom border (default) - unused, for API clarity

    Returns:
        Formatted border line
    """
    if top:
        left, mid, right, horiz = "┌", "┬", "┐", "─"
    elif middle:
        left, mid, right, horiz = "├", "┼", "┤", "─"
    else:  # bottom is the default
        left, mid, right, horiz = "└", "┴", "┘", "─"

    return (
        f"{left}{horiz * (COL_CONTAINER + 2)}{mid}"
        f"{horiz * (COL_SCHEDULE + 2)}{mid}"
        f"{horiz * (COL_COMMAND + 2)}{mid}"
        f"{horiz * (COL_NEXT_RUN + 2)}{right}"
    )


def _build_row(container: str, schedule: str, command: str, next_run: str) -> str:
    """
    Build a single table row with proper padding.

    Args:
        container: Container name
        schedule: RRULE schedule string
        command: Job command
        next_run: Next execution time

    Returns:
        Formatted table row
    """
    c = _truncate(container, COL_CONTAINER).ljust(COL_CONTAINER)
    s = _truncate(schedule, COL_SCHEDULE).ljust(COL_SCHEDULE)
    cmd = _truncate(command, COL_COMMAND).ljust(COL_COMMAND)
    nr = next_run.ljust(COL_NEXT_RUN)
    return f"│ {c} │ {s} │ {cmd} │ {nr} │"


def format_schedule_table(jobs: dict[str, Job]) -> str:
    """
    Format jobs dictionary as ASCII table.

    Args:
        jobs: Dictionary of job_id -> Job

    Returns:
        Formatted ASCII table with box drawing characters
    """
    if not jobs:
        return "Active Schedule: No jobs scheduled"

    lines = [f"Active Schedule ({len(jobs)} jobs):"]
    lines.append(_build_border(top=True))
    lines.append(_build_row("Container", "Schedule", "Command", "Next Run"))
    lines.append(_build_border(middle=True))

    for job in jobs.values():
        # Extract RRULE string representation
        rrule_str = str(job.rrule).split("\n")[0]  # First line only
        if rrule_str.startswith("RRULE:"):
            rrule_str = rrule_str[6:]  # Remove "RRULE:" prefix

        next_run_str = job.next_run.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(_build_row(job.container_name, rrule_str, job.command, next_run_str))

    lines.append(_build_border(_bottom=True))
    return "\n".join(lines)


def format_next_execution(jobs: dict[str, Job]) -> str | None:
    """
    Format next execution message.

    Args:
        jobs: Dictionary of job_id -> Job

    Returns:
        Formatted message with next execution time and relative time, or None if no jobs
    """
    if not jobs:
        return None

    now = datetime.now(UTC)
    next_job = min(jobs.values(), key=lambda j: j.next_run)
    time_until = (next_job.next_run - now).total_seconds()
    relative = _format_relative_time(time_until)

    return f"Next job execution: {next_job.next_run.strftime('%Y-%m-%d %H:%M:%S')} ({relative})"
