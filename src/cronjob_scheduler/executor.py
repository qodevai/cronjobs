"""Job execution in Docker containers."""

import asyncio
import logging
import time

import aiodocker
from aiodocker.exceptions import DockerError
from opentelemetry.propagate import inject
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import Status, StatusCode

from cronjob_scheduler.models import Job
from cronjob_scheduler.telemetry import (
    cronjob_duration,
    cronjob_executions,
    record_last_run,
    tracer,
)

logger = logging.getLogger(__name__)

CONTAINER_NOT_FOUND_STATUS = 404
EXEC_TIMEOUT_SECONDS = 60 * 60  # 1 hour


async def _stream_exec_output(exec_instance: object, job_id: str) -> list[str]:
    """
    Stream and collect output from exec instance.

    Args:
        exec_instance: Docker exec instance
        job_id: Job ID for logging

    Returns:
        List of output lines

    Raises:
        TimeoutError: If execution exceeds timeout
    """
    output_lines = []
    try:
        async with asyncio.timeout(EXEC_TIMEOUT_SECONDS):
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
        logger.warning("Job %s execution timed out after %d seconds", job_id, EXEC_TIMEOUT_SECONDS)
        raise

    return output_lines


def _trace_context_env() -> dict[str, str]:
    """
    Build environment variables carrying the current W3C trace context.

    Injects the active span's context into a carrier and exposes it as upper-cased
    environment variables (``TRACEPARENT`` / ``TRACESTATE``) for the executed command, so
    an instrumented job can extract them and continue the same trace. Returns an empty dict
    when telemetry is disabled (the active span context is then invalid and nothing is
    injected), which leaves the executed command's environment untouched.
    """
    carrier: dict[str, str] = {}
    inject(carrier)
    return {key.upper(): value for key, value in carrier.items()}


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

    start = time.monotonic()
    status = "error"
    exit_code = -1

    with tracer.start_as_current_span("cronjob.execute", kind=SpanKind.PRODUCER) as span:
        span.set_attribute("cronjob.job_id", job.id)
        span.set_attribute("cronjob.container_id", container_id_short)
        span.set_attribute("cronjob.container_name", job.container_name)
        span.set_attribute("cronjob.command", job.command)

        try:
            # Get the container
            container = await docker_client.containers.get(job.container_id)

            # Parse command into list for exec
            # If command is already a string, we need to pass it to shell
            cmd = ["/bin/sh", "-c", job.command]

            # Execute command in container - capture output for logging. The trace context
            # is passed through so an instrumented job can join this execution's trace.
            exec_instance = await container.exec(
                cmd=cmd,
                stdout=True,
                stderr=True,
                environment=_trace_context_env() or None,
            )

            # Start execution and capture output
            try:
                output_lines = await _stream_exec_output(exec_instance, job.id)
            except TimeoutError:
                status = "timeout"
                span.set_status(Status(StatusCode.ERROR, "execution timed out"))
                return -1

            # Extract exit code from result
            inspect = await exec_instance.inspect()
            exit_code = inspect.get("ExitCode", 0)

            # Log output for all executions
            output = "".join(output_lines).strip() if output_lines else "(no output)"

            if exit_code == 0:
                status = "success"
                if output:
                    logger.info(
                        "Job %s completed successfully (exit code: %d). Output: %s",
                        job.id,
                        exit_code,
                        output[:200],  # Limit output to 200 chars
                    )
                else:
                    logger.info(
                        "Job %s completed successfully (exit code: %d)",
                        job.id,
                        exit_code,
                    )
            else:
                status = "failure"
                span.set_status(Status(StatusCode.ERROR, f"exit code {exit_code}"))
                logger.warning(
                    "Job %s failed with exit code %d. Output: %s",
                    job.id,
                    exit_code,
                    output[:200],  # Limit output to 200 chars
                )

            return exit_code

        except DockerError as e:
            status = "error"
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, "docker error"))
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
            status = "timeout"
            span.set_status(Status(StatusCode.ERROR, "docker api timeout"))
            # Timeout waiting for Docker API
            logger.error(
                "Timeout executing job %s in container %s (Docker API timeout)",
                job.id,
                container_id_short,
            )
            return -1

        except Exception as e:
            status = "error"
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, "unexpected error"))
            # Any other error during execution
            logger.exception(
                "Unexpected error executing job %s in container %s",
                job.id,
                container_id_short,
            )
            return -1

        finally:
            span.set_attribute("cronjob.status", status)
            span.set_attribute("cronjob.exit_code", exit_code)
            metric_attributes = {
                "cronjob.job_id": job.id,
                "cronjob.container_name": job.container_name,
                "cronjob.status": status,
            }
            cronjob_executions.add(1, metric_attributes)
            cronjob_duration.record(time.monotonic() - start, metric_attributes)
            record_last_run(job.id, job.container_name, status)
