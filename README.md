# Cronjob Scheduler

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/qodevai/cronjobs/actions/workflows/ci.yml/badge.svg)](https://github.com/qodevai/cronjobs/actions/workflows/ci.yml)
[![Docker Hub](https://img.shields.io/docker/v/qodev/cronjobs?label=docker&logo=docker)](https://hub.docker.com/r/qodev/cronjobs)

A Docker-native cronjob scheduler that monitors containers and executes scheduled tasks based on RRULE labels.

## Features

- **RRULE-based scheduling**: Uses RFC 5545 recurrence rules instead of cron syntax
- **Docker-native**: Monitors Docker containers via labels
- **Event-driven**: Automatically detects container changes
- **Concurrent execution**: Runs multiple jobs in parallel
- **No persistent storage**: Fully in-memory, stateless design
- **OpenTelemetry-ready**: Optional, vendor-neutral metrics and traces, including trace-context propagation into executed jobs ([details](#opentelemetry-metrics--traces))

## Quick Start

### Option 1: Using Docker Hub (Recommended)

```yaml
version: '3.8'

services:
  scheduler:
    image: qodev/cronjobs:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - LOG_LEVEL=INFO  # Optional: DEBUG, INFO, WARNING, ERROR
    restart: unless-stopped

  # Example worker container with scheduled job
  worker:
    image: python:3.12-slim
    labels:
      ai.qodev.cronjobs: |
        FREQ=MINUTELY;INTERVAL=5 => echo "Running every 5 minutes"
        FREQ=HOURLY => python /app/hourly_task.py
    command: sleep infinity
```

### Option 2: Build from Source

```yaml
version: '3.8'

services:
  scheduler:
    build: https://github.com/qodevai/cronjobs.git
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped
```

Then start with:
```bash
docker-compose up -d
```

### Label Format

Add jobs to containers using the `ai.qodev.cronjobs` label:

```
ai.qodev.cronjobs: '<RRULE> => <command>'
```

**RRULE can be uppercase, lowercase, or mixed case** - all are supported.

**Examples:**

```
# Every 5 minutes (uppercase)
ai.qodev.cronjobs: 'FREQ=MINUTELY;INTERVAL=5 => python sync.py'

# Every 5 minutes (lowercase works too!)
ai.qodev.cronjobs: 'freq=minutely;interval=5 => python sync.py'

# Daily at 2 AM
ai.qodev.cronjobs: 'FREQ=DAILY;BYHOUR=2;BYMINUTE=0 => python cleanup.py'

# Weekdays at 9 AM
ai.qodev.cronjobs: 'FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9 => python report.py'

# Multiple jobs (newline-separated)
ai.qodev.cronjobs: |
  FREQ=HOURLY => python hourly.py
  FREQ=DAILY;BYHOUR=3 => python daily.py
```

### RRULE Patterns

Common patterns:

- `FREQ=MINUTELY;INTERVAL=5` - Every 5 minutes
- `FREQ=HOURLY` - Every hour (on the hour)
- `FREQ=DAILY;BYHOUR=14;BYMINUTE=30` - Daily at 2:30 PM
- `FREQ=WEEKLY;BYDAY=MO` - Every Monday
- `FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=9` - Mon/Wed/Fri at 9 AM
- `FREQ=MONTHLY;BYMONTHDAY=1` - First day of each month

See [RFC 5545](https://tools.ietf.org/html/rfc5545) for full RRULE specification.

## Development

### Setup

```bash
# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run specific test file
uv run pytest tests/test_scheduler.py -v
```

### Project Structure

```
src/cronjob_scheduler/
  models.py          # Job model and label parsing
  scheduler.py       # Job scheduling logic
  executor.py        # Job execution in containers
  docker_watcher.py  # Container monitoring
  main.py            # Main orchestrator
```

### Running Locally

```bash
# Build and run with docker-compose
docker-compose up --build

# Check health
curl http://localhost:8080/health
```

## Architecture

1. **Docker Watcher**: Monitors container events (start/stop/die) and syncs jobs
2. **Scheduler**: Event-driven scheduler that sleeps until next job is due
3. **Executor**: Runs commands in target containers via Docker exec
4. **Jobs are anchored**: All schedules align to `2025-01-01T00:00:00Z` for consistent timing

### Execution Flow

1. Scheduler scans containers for `ai.qodev.cronjobs` labels on startup
2. Parses RRULE and calculates next run time for each job
3. Sleeps until next job is due (event-driven, no polling)
4. When job is due, fires it via `docker exec` (non-blocking)
5. Immediately calculates next run time and continues
6. Container changes trigger immediate re-sync

## Configuration

### Logging

Configure logging verbosity with the `LOG_LEVEL` environment variable:

```yaml
services:
  scheduler:
    image: qodev/cronjobs:latest
    environment:
      - LOG_LEVEL=DEBUG  # DEBUG, INFO (default), WARNING, ERROR
```

**Log levels:**
- `DEBUG`: Detailed information for diagnosing problems (sleep timings, job registration, etc.)
- `INFO`: General informational messages (jobs found, jobs executed, container events)
- `WARNING`: Warning messages (invalid labels, failed jobs)
- `ERROR`: Error messages only

### OpenTelemetry (metrics & traces)

The scheduler can export [OpenTelemetry](https://opentelemetry.io/) metrics and traces over
OTLP/HTTP. It is **opt-in and vendor-neutral** — configured entirely through the standard
`OTEL_*` environment variables, with no specific backend assumed. When no OTLP endpoint is
configured, telemetry stays a no-op and adds no overhead.

#### Enabling it

Set an OTLP endpoint (and, for most backends, auth headers and resource attributes):

```yaml
services:
  scheduler:
    image: qodev/cronjobs:latest
    environment:
      # Required to enable telemetry — base OTLP/HTTP endpoint (paths are appended automatically)
      - OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.example.com
      # Optional: headers for authenticated collectors (e.g. HTTP Basic / API key)
      - OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64>
      # Optional: identify this service in your backend
      - OTEL_RESOURCE_ATTRIBUTES=service.namespace=myproject,service.name=scheduler
```

Recognised environment variables (all standard OpenTelemetry SDK variables):

| Variable | Purpose |
| --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Base OTLP/HTTP endpoint. **Telemetry is disabled unless this (or a signal-specific endpoint) is set.** The exporter appends `/v1/metrics` and `/v1/traces`. |
| `OTEL_EXPORTER_OTLP_HEADERS` | Comma-separated headers, e.g. `Authorization=Basic abc123`. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | Defaults to `http/protobuf` (the only protocol bundled). |
| `OTEL_RESOURCE_ATTRIBUTES` | Resource attributes, e.g. `service.namespace=...,service.name=...`. |
| `OTEL_SERVICE_NAME` | Shorthand for `service.name` (defaults to `cronjob-scheduler`). |
| `OTEL_SDK_DISABLED` | Set to `true` to force telemetry off even when an endpoint is configured. |

#### What gets emitted

**Metrics**

| Metric | Type | Description |
| --- | --- | --- |
| `cronjob.executions` | Counter | One increment per job run. |
| `cronjob.duration` | Histogram (seconds) | Wall-clock duration of each run. |
| `cronjob.last_run_failed` | Gauge | `1` if a job's most recent run did not succeed, else `0`. |

`cronjob.executions` and `cronjob.duration` carry the attributes `cronjob.job_id`,
`cronjob.container_name`, and `cronjob.status` (`success` \| `failure` \| `timeout` \|
`error`); `cronjob.last_run_failed` carries `cronjob.job_id` and `cronjob.container_name`.

For alerting, prefer `cronjob.last_run_failed`: it holds each job's most recent outcome
until that job runs again, so an alert on `latest(cronjob.last_run_failed) == 1` (grouped
by `cronjob.job_id`) **stays firing until the same job succeeds**, rather than resolving
once the failure ages out of a window. Alerting on `cronjob.executions` where
`cronjob.status != "success"` instead is windowed, so a brief periodic failure flaps
(fires, then auto-resolves when the window clears) rather than latching.

**Traces**

Each run produces one `cronjob.execute` span (service = the scheduler) carrying `cronjob.job_id`,
`cronjob.container_name`, `cronjob.command`, `cronjob.exit_code`, and `cronjob.status`. The span
is marked as an error when the job exits non-zero, times out, or fails to start.

#### Linking the executed job to the trace

Before running a command, the scheduler injects the active span's
[W3C trace context](https://www.w3.org/TR/trace-context/) into the command's environment as
`TRACEPARENT` (and `TRACESTATE` when present). An OpenTelemetry-instrumented job can extract it
and **continue the same trace**, so the job's own spans appear as children of `cronjob.execute` —
giving you one end-to-end trace per run, even across services.

The scheduler only *exposes* the standard variables; how (and whether) a job uses them is up to
that job. In Python, for example:

```python
import os
from opentelemetry.propagate import extract
from opentelemetry import trace

tracer = trace.get_tracer(__name__)
parent = extract({
    "traceparent": os.environ.get("TRACEPARENT", ""),
    "tracestate": os.environ.get("TRACESTATE", ""),
})
with tracer.start_as_current_span("my-job", context=parent):
    ...  # this span (and its children) join the scheduler's trace
```

> **Note:** language SDKs do not auto-read `TRACEPARENT` from the environment, so each job that
> wants to be linked needs a few lines like the above. Jobs that don't opt in still get the
> standalone `cronjob.execute` span (duration + status); linking simply lights up per job.

### Requirements

- Docker socket access (`/var/run/docker.sock`)
- Python 3.11+

## Troubleshooting

### Jobs not running

1. **Check scheduler logs:**
   ```bash
   docker logs cronjob-scheduler
   ```
   or if using compose:
   ```bash
   docker-compose logs scheduler
   ```

2. **Verify RRULE syntax:**
   - Use uppercase: `FREQ=HOURLY` (lowercase also works but uppercase is recommended)
   - Check RFC 5545 specification for valid patterns
   - Test your RRULE at [rrule.dev](https://rrule.dev)

3. **Verify container is running:**
   ```bash
   docker ps
   ```

4. **Check if scheduler detected your container:**
   - With `LOG_LEVEL=INFO`, you'll see: `Found X job(s) in container ...`
   - If not shown, verify the `ai.qodev.cronjobs` label is set correctly

### Invalid label errors

If you see "Invalid cronjob label" warnings:
- Check that you're using `=>` separator (not `=` or `:`)
- Ensure both RRULE and command are present
- For multi-line labels, use YAML's `|` syntax:
  ```yaml
  labels:
    ai.qodev.cronjobs: |
      FREQ=HOURLY => command1
      FREQ=DAILY => command2
  ```

### Commands not executing in container

1. **Test manually:**
   ```bash
   docker exec <container-name> sh -c "your-command"
   ```

2. **Check if binaries exist in container**
3. **Review command output in logs** (visible with `LOG_LEVEL=DEBUG`)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Security

See [SECURITY.md](SECURITY.md) for security considerations and reporting vulnerabilities.

## License

MIT
