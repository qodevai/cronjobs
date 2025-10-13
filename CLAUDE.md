# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Docker-native cronjob scheduler that uses RRULE (RFC 5545 recurrence rules) instead of traditional cron syntax. It monitors Docker containers for `ai.qodev.cronjobs` labels and executes scheduled tasks in those containers using `docker exec`.

**Key characteristics:**
- Event-driven, async-first architecture (asyncio)
- Stateless - no persistent storage, rebuilds state from container labels
- Uses `aiodocker` for Docker API interactions
- Jobs are anchored to `2025-01-01T00:00:00Z` for consistent schedule alignment
- Alpine-compatible with minimal dependencies (only 2 runtime deps)
- Production image uses Alpine Linux for enhanced security (88% fewer CVEs)

## Development Commands

**Quick Start:**
```bash
make help          # Show all available commands
make install       # Install all dependencies
make install-hooks # Install pre-commit hooks (recommended!)
make check         # Run all quality checks
make test          # Run tests with coverage
```

**For comprehensive command documentation, see [CONTRIBUTING.md](CONTRIBUTING.md).**

### Key Commands (Most Used)

```bash
# Development workflow
make check         # Lint, format-check, typecheck, typos (run before commit)
make test          # Run tests with coverage
make dev           # Start docker-compose environment
make lint-fix      # Auto-fix linting issues

# Direct uv commands (when you need more control)
uv run pytest tests/test_scheduler.py      # Run specific test file
uv run pytest -k test_name                 # Run tests matching pattern
uv run pytest --durations=10               # Show slowest tests
uv run ruff check --fix                    # Fix auto-fixable issues
```

### Pre-commit Hooks

Install once, runs automatically on every commit:
```bash
make install-hooks
```

See [CONTRIBUTING.md](CONTRIBUTING.md#pre-commit-hooks) for details.

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

# Build specific stages
docker build -t cronjob-scheduler:test --target test .  # For running tests
docker build -t cronjob-scheduler:prod --target production .  # For production

# Run tests in Docker
docker run --rm cronjob-scheduler:test uv run pytest
```

### Security Scanning
```bash
# Scan for vulnerabilities with Docker Scout (requires Docker Desktop or login)
docker scout cves <image-name>

# Compare vulnerability counts
docker scout cves qodev/cronjobs:latest  # Check current vulnerabilities

# Get recommendations for base image updates
docker scout recommendations <image-name>
```

**Current security baseline** (Alpine production image):
- 3 vulnerabilities total (1 MEDIUM, 2 LOW)
- Main remaining CVE: pip symlink issue (CVE-2025-8869) - low risk for containers
- 88% reduction from debian-slim base (was 25 vulnerabilities)

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
   - `parse_cronjob_label()`: Parses `ai.qodev.cronjobs` label format (`RRULE => command`)
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

1. On startup, `docker_watcher` scans all running containers for `ai.qodev.cronjobs` labels
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

Containers are scheduled using an `ai.qodev.cronjobs` label:

```yaml
labels:
  ai.qodev.cronjobs: |
    RRULE => command
    RRULE => another command
```

**Important:** RRULE syntax is case-insensitive (`FREQ=HOURLY` or `freq=hourly` both work). The parser normalizes to uppercase before passing to `dateutil.rrule`.

Examples:
- `FREQ=MINUTELY;INTERVAL=5 => python sync.py`
- `FREQ=DAILY;BYHOUR=2;BYMINUTE=0 => python cleanup.py`
- `FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=9 => python report.py`

**Backward compatibility:** The label name is configurable via the `WATCH_LABEL` environment variable. To use the old label name, set `WATCH_LABEL=cronjob`.

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
  - Both are Alpine-compatible (pure Python or provide musllinux wheels)
  - `aiohttp` (aiodocker dependency) has C extensions but provides Alpine wheels
- **Dev deps**: Include pyright which requires Node.js (glibc-dependent)
- **Ruff**: Strict linting enabled (see `[tool.ruff.lint]` for active rules)
- **Pyright**: Basic type checking with some aiodocker warnings disabled due to incomplete stubs
  - Requires Node.js, which is why test stage uses debian-slim
- **Pytest**: Async mode is auto-enabled

### Dependency Compatibility Notes

**Alpine-compatible** (work with musl libc):
- ✅ aiodocker - pure Python
- ✅ python-dateutil - pure Python
- ✅ aiohttp - has C extensions but provides musllinux wheels
- ✅ pytest, ruff - work fine on Alpine

**NOT Alpine-compatible** (require glibc):
- ❌ pyright - requires Node.js which needs glibc for prebuilt binaries
- This is why the test stage uses `python:3.12-slim` instead of Alpine

### Dockerfile

The project uses a **hybrid multi-stage Docker build strategy**:

**Production stage** (`FROM python:3.12-alpine`):
- Uses Alpine Linux for minimal attack surface
- Only 3 vulnerabilities (vs 25 in debian-slim)
- ~51 MB image size (24 MB smaller than slim)
- Includes only runtime dependencies

**Test stage** (`FROM python:3.12-slim`):
- Uses debian-slim for development tool compatibility
- Required for pyright (needs Node.js with glibc)
- Includes all dev dependencies (pytest, ruff, pyright)
- Only used in CI, never deployed to production

**Why this hybrid approach?**
- Alpine's musl libc is incompatible with Node.js prebuilt binaries
- Pyright requires Node.js and is essential for CI type checking
- Production doesn't need dev tools, so can use Alpine for security
- This gives us the best of both worlds: security in production, compatibility in CI

The scheduler runs as a container with `/var/run/docker.sock` mounted read-only.

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
- **Path filtering**: Only runs when relevant files change (src/, tests/, pyproject.toml, Dockerfile, etc.)
- **Jobs**:
  1. **changes** - Detects which files changed to skip unnecessary builds
  2. **test** - Runs all code quality checks and tests:
     - Build test stage Docker image (debian-slim based for pyright)
     - Run ruff check and format validation
     - Run pyright type checking (requires Node.js/glibc)
     - Run pytest with coverage and duration tracking (`--durations=10`)
     - Upload coverage to Codecov
  3. **e2e** - End-to-end integration tests with docker-compose
- **Important**: CI uses the test stage which is debian-slim based, NOT Alpine
- **Why**: pyright is a required CI step and needs Node.js with glibc
- **Optimizations**:
  - Path filtering prevents unnecessary CI runs on docs-only changes
  - Job timeouts prevent hanging tests
  - Emojis in step names for better readability
  - Automatic cancellation of outdated workflow runs

### Typos Workflow (`.github/workflows/typos.yml`)
- **Triggers**: Push to main, all PRs
- **Purpose**: Automatically check for typos in code, docs, and comments
- **Uses**: `crate-ci/typos` action with configuration from `pyproject.toml`
- **Benefits**: Catches spelling errors before they reach production

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

### Alpine Linux Gotchas

7. **Node.js incompatibility**: Node.js prebuilt binaries don't work on Alpine's musl libc. This affects tools like pyright. Solution: Use debian-slim for test stage, Alpine for production.

8. **Multi-stage flexibility**: Docker multi-stage builds can use different base images per stage. This allows optimal images for different purposes (test vs production).

9. **C extension compatibility**: Check if Python packages with C extensions provide musllinux wheels:
   ```bash
   # Check in uv.lock for wheel types
   grep "musllinux" uv.lock  # Alpine-compatible
   grep "manylinux" uv.lock  # Needs glibc (debian/ubuntu)
   ```

10. **Security vs compatibility tradeoff**: Alpine gives better security (fewer CVEs) but may have compatibility issues with some tools. Always check CI tool requirements before migrating.

11. **Quick Alpine compatibility check**: Before migrating to Alpine, verify:
    - All runtime dependencies are pure Python or have musllinux wheels
    - CI tools don't require glibc (especially Node.js-based tools)
    - No direct system package dependencies (apt vs apk)

## Git Conventions

This project follows conventional commit format and structured branch naming for consistency and clarity.

### Commit Message Format

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `chore`: Maintenance tasks (dependencies, configs)
- `refactor`: Code restructuring without behavior changes
- `test`: Adding or updating tests
- `ci`: CI/CD pipeline changes
- `perf`: Performance improvements

**Examples:**
```bash
feat(scheduler): add support for cron syntax fallback
fix(executor): handle race condition when container disappears
docs: update CLAUDE.md with Alpine migration insights
chore(deps): update aiodocker to 0.24.0
refactor(models): extract label parsing into separate function
test(scheduler): add test for concurrent job execution
ci: add Docker Scout vulnerability scanning
```

### Branch Naming

Use descriptive branch names with type prefixes:

```
<type>/<description-in-kebab-case>
```

**Examples:**
- `feat/add-cron-syntax-support`
- `fix/container-race-condition`
- `docs/add-development-guidelines`
- `chore/update-dependencies`
- `refactor/extract-parsing-logic`
- `test/add-integration-tests`

**Special branches:**
- `main` - Production-ready code
- `security/*` - Security-related fixes (CVEs, vulnerabilities)

### Pull Request Guidelines

1. **Title**: Use same format as commit messages
2. **Description**: Include:
   - Summary of changes
   - Why the change is needed
   - Test plan or how to verify
   - Link to related issues if applicable
3. **Size**: Keep PRs focused and reasonably sized
4. **Tests**: Ensure all tests pass before requesting review
5. **Documentation**: Update relevant docs (README, CLAUDE.md, CONTRIBUTING.md)
