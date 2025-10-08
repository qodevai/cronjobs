# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Docker-native cronjob scheduler that uses RRULE (RFC 5545 recurrence rules) instead of traditional cron syntax. It monitors Docker containers for `cronjob` labels and executes scheduled tasks in those containers using `docker exec`.

**Key characteristics:**
- Event-driven, async-first architecture (asyncio)
- Stateless - no persistent storage, rebuilds state from container labels
- Uses `aiodocker` for Docker API interactions
- Jobs are anchored to `2025-01-01T00:00:00Z` for consistent schedule alignment

## Development Commands

### Testing
```bash
# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_scheduler.py

# Run specific test
uv run pytest tests/test_scheduler.py::test_register_job_calculates_next_run

# Run with coverage
uv run pytest --cov=cronjob_scheduler --cov-report=html
```

### Code Quality
```bash
# Format code
uv run ruff format

# Lint code
uv run ruff check

# Fix auto-fixable linting issues
uv run ruff check --fix

# Type checking
uv run pyright
```

### Local Testing with Docker
```bash
# Build and run the scheduler with example containers
docker-compose up --build

# View scheduler logs
docker-compose logs -f scheduler

# View logs from a specific background shell
docker logs cronjob-scheduler

# Stop everything
docker-compose down
```

### Dependency Management
```bash
# Install all dependencies including dev dependencies
uv sync --all-extras

# Add a new dependency
# Edit pyproject.toml, then run:
uv sync
```

## Architecture

### Core Components

1. **models.py** - Data structures and label parsing
   - `Job`: Dataclass representing a scheduled job
   - `parse_cronjob_label()`: Parses `cronjob` label format (`RRULE => command`)
   - `ANCHOR`: Fixed datetime (2025-01-01 00:00:00 UTC) used for all schedule calculations

2. **scheduler.py** - Event-driven job scheduling
   - `Scheduler`: Manages job registration and timing
   - Uses `asyncio.Event` for wake-ups (no polling!)
   - `register_job()`: Adds job and calculates initial `next_run`
   - `wait_for_due_jobs()`: Sleeps until jobs are due, then returns them (with `next_run` already updated)

3. **executor.py** - Job execution via Docker
   - `execute_job()`: Executes job command in target container using `docker exec`
   - Commands are executed via `/bin/sh -c` for shell support
   - Returns exit code (0 = success, -1 = error)

4. **docker_watcher.py** - Container event monitoring
   - `watch_containers()`: Listens to Docker events (start/stop/die/destroy)
   - `sync_jobs_from_containers()`: Scans all containers and syncs jobs to scheduler
   - Automatically removes jobs when containers disappear

5. **main.py** - Application orchestration
   - `run_scheduler_loop()`: Main loop that waits for due jobs and fires them concurrently
   - Uses `asyncio.create_task()` for fire-and-forget execution
   - Handles graceful shutdown via SIGTERM/SIGINT

### Execution Flow

1. On startup, `docker_watcher` scans all running containers for `cronjob` labels
2. Each job is parsed and registered with the `Scheduler`
3. `Scheduler` calculates `next_run` time for each job using its RRULE
4. `run_scheduler_loop()` waits for jobs to become due (event-driven sleep)
5. When jobs are due, they're executed concurrently via `docker exec` (fire-and-forget)
6. After execution, `next_run` is immediately recalculated
7. Container lifecycle events trigger re-sync of all jobs

### Key Design Patterns

**Event-driven scheduling**: The scheduler uses `asyncio.Event` and `asyncio.wait_for()` with timeout to wake up either when a job is due OR when jobs are added/removed. This eliminates polling.

**Fire-and-forget execution**: Jobs are executed using `asyncio.create_task()` without awaiting. This allows the scheduler to immediately move to the next job without blocking on execution.

**Schedule anchoring**: All RRULE schedules use the same `ANCHOR` datetime (2025-01-01 00:00:00 UTC) as their start point. This ensures consistent timing - e.g., "every 5 minutes" will always align to :00, :05, :10, etc.

**Stateless design**: No database or persistent storage. All state is rebuilt from container labels on startup and after container events.

## Label Format

Containers are scheduled using a `cronjob` label:

```yaml
labels:
  cronjob: |
    RRULE => command
    RRULE => another command
```

**Important:** RRULE syntax is case-insensitive (`FREQ=HOURLY` or `freq=hourly` both work). The parser normalizes to uppercase before passing to `dateutil.rrule`.

Examples:
- `FREQ=MINUTELY;INTERVAL=5 => python sync.py`
- `FREQ=DAILY;BYHOUR=2;BYMINUTE=0 => python cleanup.py`
- `FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=9 => python report.py`

## Testing Approach

This project follows TDD principles:
1. Tests use pytest with async support (`pytest-asyncio`)
2. Most tests use mocks (`pytest-mock`) to avoid real Docker dependencies
3. Test structure follows Arrange-Act-Assert pattern
4. Fixtures are defined in individual test files

**Test coverage:**
- `test_models.py` - Label parsing, RRULE validation, Job creation
- `test_scheduler.py` - Job registration, timing logic, event-driven wake-ups
- `test_executor.py` - Command execution, error handling
- `test_docker_watcher.py` - Container monitoring, job synchronization

## Configuration Notes

### pyproject.toml
- **Runtime deps**: Only `aiodocker` and `python-dateutil` (lightweight!)
- **Ruff**: Strict linting enabled (see `[tool.ruff.lint]` for active rules)
- **Pyright**: Basic type checking with some aiodocker warnings disabled due to incomplete stubs
- **Pytest**: Async mode is auto-enabled

### Dockerfile
Not in this snapshot, but the scheduler runs as a container with `/var/run/docker.sock` mounted read-only.

## Logging

The application uses Python's standard `logging` module throughout:

**Log Levels:**
- `DEBUG`: Detailed troubleshooting (sleep timings, job registration, RRULE parsing)
- `INFO`: Operational events (jobs due, jobs executed, container events) - **default**
- `WARNING`: Non-fatal issues (invalid labels, failed jobs with output)
- `ERROR`: Errors preventing operations (Docker errors, parsing failures)

**Configuration:**
Set via `LOG_LEVEL` environment variable in main.py:66. Format is: `timestamp [level] module: message`

**Per-module loggers:**
- `cronjob_scheduler.main` - Startup, shutdown, task management
- `cronjob_scheduler.docker_watcher` - Container scanning, job sync
- `cronjob_scheduler.scheduler` - Job timing, wake-ups
- `cronjob_scheduler.executor` - Job execution, exit codes, output capture
- `cronjob_scheduler.models` - Label parsing, RRULE validation

## GitHub Workflows

### CI Workflow (`.github/workflows/ci.yml`)
- **Triggers**: Push to main, all PRs
- **Matrix**: Python 3.11, 3.12, 3.13
- **Steps**: ruff check, ruff format, pyright, pytest with coverage
- **Coverage**: Uploads to Codecov (Python 3.11 only)

### Docker Publish (`.github/workflows/docker-publish.yml`)
- **Triggers**: Push to main, version tags (`v*`)
- **Registry**: Docker Hub (`qodev/cronjobs`)
- **Platforms**: linux/amd64, linux/arm64
- **Tags**:
  - `latest` (on main branch)
  - `main` (on main branch)
  - Semantic versions from tags (e.g., `v1.2.3` → `1.2.3`, `1.2`, `1`)
- **Secrets needed**: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`

**To publish a new version:**
1. Update version in `pyproject.toml`
2. Commit and push
3. Create and push a tag: `git tag v1.0.0 && git push origin v1.0.0`
4. GitHub Actions will automatically build and push to Docker Hub

## Common Gotchas

1. **Accessing scheduler internals**: Tests sometimes access `scheduler._jobs` directly (it's a private dict). This is acceptable for testing but avoid in production code.

2. **Time-based tests**: Use `pytest-mock` to freeze time or mock `datetime.now()`. RRULE calculations are anchored to `ANCHOR`, so tests should account for this.

3. **Async context**: All main functions are async. Use `@pytest.mark.asyncio` for tests.

4. **Docker socket permissions**: The scheduler needs read access to `/var/run/docker.sock`. In docker-compose, mount it with `:ro` flag.

5. **Case sensitivity**: RRULEs are normalized to uppercase internally, but the user-facing API accepts any case.

6. **Job output capture**: The executor captures job output for logging when jobs fail (executor.py:52-58). Successful jobs only log at DEBUG level.
