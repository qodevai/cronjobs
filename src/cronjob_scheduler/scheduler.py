"""Job scheduler with event-driven timing."""

import asyncio
import logging
from datetime import UTC, datetime

from cronjob_scheduler.formatting import format_next_execution, format_schedule_table
from cronjob_scheduler.models import Job

logger = logging.getLogger(__name__)


class Scheduler:
    """Manages job scheduling with event-driven wake-ups."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._next_due = asyncio.Event()

    def get_job_ids(self) -> set[str]:
        """
        Return set of current job IDs.

        Returns:
            Set of job IDs currently scheduled
        """
        return set(self._jobs.keys())

    def get_jobs_by_container(self, container_ids: set[str]) -> list[str]:
        """
        Get job IDs that do NOT belong to the given container IDs.

        Args:
            container_ids: Set of container IDs to check against

        Returns:
            List of job IDs for containers not in the provided set
        """
        return [
            job_id for job_id, job in self._jobs.items() if job.container_id not in container_ids
        ]

    def log_schedule(self) -> None:
        """Log the current schedule table at INFO level."""
        table = format_schedule_table(self._jobs)
        logger.info("\n%s", table)

        next_exec = format_next_execution(self._jobs)
        if next_exec:
            logger.info(next_exec)

    def register_job(self, job: Job) -> None:
        """
        Register a new job and calculate its first run time.

        Args:
            job: Job to register
        """
        # Calculate initial next_run
        now = datetime.now(UTC)
        job.next_run = job.rrule.after(now)

        self._jobs[job.id] = job
        logger.debug("Registered job %s, next run at %s", job.id, job.next_run)
        self._next_due.set()  # Wake up scheduler

    def unregister_job(self, job_id: str) -> None:
        """
        Remove a job from the schedule.

        Args:
            job_id: ID of job to remove
        """
        removed_job = self._jobs.pop(job_id, None)
        if removed_job:
            logger.debug("Unregistered job %s", job_id)
        self._next_due.set()  # Wake up scheduler to recalculate

    async def wait_for_due_jobs(self) -> list[Job]:
        """
        Wait until jobs are due and return them.

        Calculates next_run for each job before returning.
        Blocks until at least one job is due.

        Returns:
            List of jobs that are due (with next_run already updated)
        """
        while True:
            now = datetime.now(UTC)
            due = []

            # Find and update due jobs
            for job in self._jobs.values():
                if job.next_run <= now:
                    time_diff = (now - job.next_run).total_seconds()
                    if time_diff > 1:
                        logger.debug(
                            "Job %s is overdue by %.1f seconds (was scheduled for %s)",
                            job.id,
                            time_diff,
                            job.next_run,
                        )
                    # Calculate next run BEFORE returning to runner
                    next_occurrence = job.rrule.after(now)
                    logger.debug(
                        "Job %s next execution scheduled for %s",
                        job.id,
                        next_occurrence,
                    )
                    job.next_run = next_occurrence
                    due.append(job)

            if due:
                return due

            # Calculate sleep duration until next job
            if self._jobs:
                next_run = min(job.next_run for job in self._jobs.values())
                sleep_duration = (next_run - datetime.now(UTC)).total_seconds()

                if sleep_duration > 0:
                    logger.debug(
                        "Sleeping for %.2f seconds until next job at %s",
                        sleep_duration,
                        next_run,
                    )
                    try:
                        # Wait for either timeout or manual wake-up
                        await asyncio.wait_for(self._next_due.wait(), timeout=sleep_duration)
                        self._next_due.clear()
                        logger.debug("Woken up early due to job registration/unregistration")
                        # Loop again to re-check jobs (may have changed)
                    except TimeoutError:
                        # Natural wake-up - job is due, loop again to check
                        logger.debug("Wake-up timer elapsed, checking for due jobs")
                else:
                    # Job is already due, loop immediately
                    logger.debug("Job is already overdue, executing immediately")
            else:
                # No jobs scheduled - wait for registration
                logger.debug("No jobs scheduled, waiting for job registration")
                await self._next_due.wait()
                self._next_due.clear()
