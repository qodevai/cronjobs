"""Job execution in Docker containers."""

import asyncio
import logging

import aiodocker
from aiodocker.exceptions import DockerError

from cronjob_scheduler.models import Job

logger = logging.getLogger(__name__)

CONTAINER_NOT_FOUND_STATUS = 404


async def execute_job(docker_client: aiodocker.Docker, job: Job) -> int:
    """
    Execute a job command in its container.

    Args:
        docker_client: aiodocker.Docker client instance
        job: Job to execute

    Returns:
        Exit code from the command (0 = success, -1 = error)
    """
    container_id_short = job.container_id[:12]
    logger.info(
        "Executing job %s in container %s: %s",
        job.id,
        container_id_short,
        job.command,
    )

    try:
        # Get the container
        container = await docker_client.containers.get(job.container_id)

        # Parse command into list for exec
        # If command is already a string, we need to pass it to shell
        cmd = ["/bin/sh", "-c", job.command]

        # Execute command in container - capture output for logging
        exec_instance = await container.exec(
            cmd=cmd,
            stdout=True,
            stderr=True,
        )

        # Start execution and capture output (with timeout to avoid blocking forever)
        output_lines = []
        try:
            async with asyncio.timeout(30):  # 30 second timeout for job execution
                stream = exec_instance.start()
                while True:
                    try:
                        msg = await stream.read_out()
                        if msg is None:
                            break
                        # msg is a tuple: (stream_type, data)
                        if msg.data:
                            output_lines.append(msg.data.decode("utf-8", errors="replace"))
                    except Exception:
                        break
        except TimeoutError:
            logger.warning("Job %s execution timed out after 30 seconds", job.id)
            return -1

        # Extract exit code from result
        inspect = await exec_instance.inspect()
        exit_code = inspect.get("ExitCode", 0)

        # Log output for all executions
        output = "".join(output_lines).strip() if output_lines else "(no output)"

        if exit_code == 0:
            if output:
                logger.info(
                    "Job %s completed successfully (exit code: %d). Output: %s",
                    job.id,
                    exit_code,
                    output[:500],  # Limit output to 500 chars
                )
            else:
                logger.info(
                    "Job %s completed successfully (exit code: %d)",
                    job.id,
                    exit_code,
                )
        else:
            logger.warning(
                "Job %s failed with exit code %d. Output: %s",
                job.id,
                exit_code,
                output[:500],  # Limit output to 500 chars
            )

        return exit_code

    except DockerError as e:
        # Container not found or other Docker error
        if e.status == CONTAINER_NOT_FOUND_STATUS:
            # Container doesn't exist
            logger.error(
                "Container %s not found for job %s",
                container_id_short,
                job.id,
            )
            return -1
        # Other Docker errors
        logger.error(
            "Docker error executing job %s in container %s: %s",
            job.id,
            container_id_short,
            e,
        )
        return -1

    except TimeoutError:
        # Timeout waiting for Docker API
        logger.error(
            "Timeout executing job %s in container %s (Docker API timeout)",
            job.id,
            container_id_short,
        )
        return -1

    except Exception as e:
        # Any other error during execution
        logger.error(
            "Unexpected error executing job %s in container %s: %s",
            job.id,
            container_id_short,
            e,
            exc_info=True,
        )
        return -1
