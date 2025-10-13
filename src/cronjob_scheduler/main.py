"""Main orchestrator for cronjob scheduler."""

import asyncio
import logging
import os
import signal
from typing import NoReturn

import aiodocker

from cronjob_scheduler.docker_watcher import watch_containers
from cronjob_scheduler.executor import execute_job
from cronjob_scheduler.scheduler import Scheduler

logger = logging.getLogger(__name__)


async def run_scheduler_loop(scheduler: Scheduler, docker_client: aiodocker.Docker) -> NoReturn:
    """
    Main scheduler loop.

    Waits for due jobs and executes them concurrently without waiting for completion.
    """
    tasks: set[asyncio.Task] = set()

    def task_done_callback(task: asyncio.Task) -> None:
        """Handle task completion and log any exceptions."""
        tasks.discard(task)
        try:
            task.result()  # Raise exception if task failed
        except Exception:
            logger.exception("Task failed with exception")

    while True:
        # Wait for jobs to be due
        due_jobs = await scheduler.wait_for_due_jobs()

        # Fire all due jobs concurrently (don't wait for them)
        for job in due_jobs:
            task = asyncio.create_task(execute_job(docker_client, job))
            tasks.add(task)
            # Clean up completed tasks and log exceptions
            task.add_done_callback(task_done_callback)

        # Yield control to allow tasks to start
        await asyncio.sleep(0)


async def main_async() -> None:
    """Main async entry point."""
    # Initialize components
    docker_client = aiodocker.Docker()
    scheduler = Scheduler()

    logger.info("Cronjob scheduler starting...")

    try:
        # Run main loops concurrently
        await asyncio.gather(
            watch_containers(docker_client, scheduler),
            run_scheduler_loop(scheduler, docker_client),
        )
    except asyncio.CancelledError:
        logger.info("Shutting down gracefully...")
    finally:
        # Cleanup
        await docker_client.close()
        logger.info("Cleanup complete")


def main() -> None:
    """Main entry point."""
    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Setup signal handlers for graceful shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_task = loop.create_task(main_async())

    # Handle shutdown signals
    def handle_signal(sig: int) -> None:
        logger.info("Received signal %d, shutting down...", sig)
        main_task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    try:
        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
