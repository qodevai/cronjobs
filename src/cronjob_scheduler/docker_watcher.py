"""Docker container monitoring and job synchronization."""

import asyncio
import logging
import os

import aiodocker

from cronjob_scheduler.models import parse_cronjob_label
from cronjob_scheduler.scheduler import Scheduler

logger = logging.getLogger(__name__)

# Label to watch for cronjobs (can be overridden for testing)
WATCH_LABEL = os.getenv("WATCH_LABEL", "cronjob")


def _get_container_display_name(container_info: dict) -> str:
    """
    Extract container name for display, fallback to short ID.

    Args:
        container_info: Container info dictionary from Docker API

    Returns:
        Container name (without leading /) or short container ID
    """
    name = container_info.get("Name", "").lstrip("/")
    return name or container_info["Id"][:12]


async def sync_jobs_from_containers(docker_client: aiodocker.Docker, scheduler: Scheduler) -> None:
    """
    Sync jobs from all running containers with cronjob labels.

    Scans all containers, parses their cronjob labels, and updates the scheduler.
    Removes jobs from containers that no longer exist.

    Args:
        docker_client: aiodocker.Docker client instance
        scheduler: Scheduler instance to update
    """
    # Track job IDs before sync to detect changes
    job_ids_before = scheduler.get_job_ids()

    # Get all running containers
    containers = await docker_client.containers.list()
    logger.debug("Found %d running containers", len(containers))

    # Track current container IDs
    current_container_ids = set()
    new_jobs = []

    for container in containers:
        # Get container info as dict
        try:
            container_info = await container.show()
        except aiodocker.exceptions.DockerError as e:
            # Container may have been removed between listing and showing
            if e.status == 404:
                logger.debug("Container disappeared during sync, skipping")
                continue
            raise

        container_id = container_info["Id"]
        current_container_ids.add(container_id)

        # Check for cronjob label (using configured label key)
        labels = container_info.get("Config", {}).get("Labels", {})
        cronjob_label = labels.get(WATCH_LABEL)

        if not cronjob_label:
            continue

        # Get container name for logging and display
        container_name = _get_container_display_name(container_info)

        # Parse jobs from label
        try:
            jobs = parse_cronjob_label(
                cronjob_label,
                container_id=container_id,
                container_name=container_name,
            )
            if jobs:
                logger.debug(
                    "Found %d job(s) in container %s (%s)",
                    len(jobs),
                    container_name,
                    container_id[:12],
                )
                for job in jobs:
                    logger.debug("Job: %s => %s", job.rrule, job.command)
            new_jobs.extend(jobs)
        except ValueError as e:
            # Invalid label format - skip this container
            logger.warning(
                "Invalid cronjob label in container %s (%s): %s",
                container_name,
                container_id[:12],
                e,
            )
            continue

    # Remove jobs from containers that no longer exist
    jobs_to_remove = scheduler.get_jobs_by_container(current_container_ids)

    for job_id in jobs_to_remove:
        logger.debug("Unregistering job: %s", job_id)
        scheduler.unregister_job(job_id)

    # Register new jobs (scheduler will handle duplicates by job_id)
    existing_job_ids = scheduler.get_job_ids()
    for job in new_jobs:
        # Only register if not already registered
        if job.id not in existing_job_ids:
            logger.debug("Registering new job: %s (next run: %s)", job.id, job.next_run)
            scheduler.register_job(job)

    # Log schedule table if job IDs changed
    job_ids_after = scheduler.get_job_ids()
    if job_ids_before != job_ids_after:
        scheduler.log_schedule()


async def watch_containers(docker_client: aiodocker.Docker, scheduler: Scheduler) -> None:
    """
    Watch Docker events and sync jobs when containers change.

    Listens for container start/stop/die events and triggers job sync.

    Args:
        docker_client: aiodocker.Docker client instance
        scheduler: Scheduler instance to update
    """
    # Do initial sync
    logger.info("Starting initial container sync...")
    await sync_jobs_from_containers(docker_client, scheduler)
    logger.info("Initial sync complete")

    # Watch for container events
    logger.info("Watching for container events...")
    subscriber = docker_client.events.subscribe()

    try:
        while True:
            event = await subscriber.get()

            # Only care about container events
            if event.get("Type") != "container":
                continue

            # Only sync on lifecycle changes
            action = event.get("Action")
            if action in ("start", "stop", "die", "destroy"):
                container_id = event.get("id", "unknown")[:12]
                logger.debug("Container event: %s (%s), re-syncing jobs", action, container_id)
                # Re-sync all jobs
                await sync_jobs_from_containers(docker_client, scheduler)

    except asyncio.CancelledError:
        # Clean shutdown
        logger.debug("Container watcher shutting down")
        raise
