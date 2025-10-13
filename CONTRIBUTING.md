# Contributing to Cronjob Scheduler

We welcome all kinds of contributions! You don't need to be an expert in async Python or Docker to help out.

## Checklist

Contributions are made through [pull requests](https://help.github.com/articles/using-pull-requests/). Before sending a pull request, make sure to:

- [x] [Lint, typecheck, and format](#code-quality) your code
- [x] [Write tests](#writing-tests) for new functionality
- [x] [Run tests](#running-tests) and check that they pass
- [x] Update documentation if needed
- [x] Update [CHANGELOG.md](CHANGELOG.md) (add your changes to the Unreleased section)

_Please reach out before starting work on a large contribution._ Get in touch at [GitHub issues](https://github.com/qodevai/cronjobs/issues).

---

## Setup

### Prerequisites

You'll need the following tools installed:

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **uv** - Fast Python package manager ([Installation](https://docs.astral.sh/uv/getting-started/installation/))
- **Docker** - For integration testing ([Get Docker](https://docs.docker.com/get-docker/))
- **make** - For convenient commands (usually pre-installed on macOS/Linux)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/qodevai/cronjobs.git
cd cronjobs

# Install all dependencies (including dev dependencies)
make install

# Install pre-commit hooks (recommended!)
make install-hooks

# Verify everything works
make test
```

That's it! You're ready to start developing.

### Alternative Setup (without make)

If you don't have `make` or prefer direct commands:

```bash
# Install dependencies
uv sync --all-extras

# Install pre-commit hooks
uvx pre-commit install

# Run tests
uv run pytest
```

---

## Development Workflow

### Using Make Commands

The project includes a Makefile with convenient commands. Run `make help` to see all available commands:

```bash
make help          # Show all available commands
make check         # Run ALL checks (lint, format, typecheck, typos)
make test          # Run tests with coverage
make dev           # Start development environment with docker-compose
make lint-fix      # Fix linting issues automatically
```

See the [Makefile](Makefile) for the complete list of commands.

### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit` and catch issues early:

```bash
# Install hooks (do this once)
make install-hooks

# Run manually on all files
uvx pre-commit run --all-files

# Skip hooks temporarily (not recommended)
git commit --no-verify
```

The hooks will:
- ✅ Validate YAML, TOML, JSON syntax
- ✅ Check GitHub Actions workflows
- ✅ Find typos in code and docs
- ✅ Lint and format Python code
- ✅ Fix trailing whitespace and EOF issues

---

## Testing

### Running Tests

```bash
# Run all tests with coverage
make test

# Run tests with verbose output
make test-verbose

# Run tests without coverage (faster)
make test-fast

# Run specific test file
uv run pytest tests/test_scheduler.py

# Run specific test
uv run pytest tests/test_scheduler.py::test_register_job_calculates_next_run

# Show slowest tests
uv run pytest --durations=10
```

### Test Structure

Tests follow the Arrange-Act-Assert pattern:

- `tests/test_models.py` - Label parsing, RRULE validation, Job model
- `tests/test_scheduler.py` - Job registration, timing logic, event-driven scheduling
- `tests/test_executor.py` - Command execution in containers, error handling
- `tests/test_docker_watcher.py` - Container monitoring, job synchronization
- `tests/test_main.py` - Integration tests for main scheduler loop

### Writing Tests

Follow the TDD approach used in this project:

1. Write test first (it should fail)
2. Implement minimal code to pass
3. Refactor if needed
4. Ensure all tests still pass

**Example test:**

```python
import pytest
from cronjob_scheduler.models import Job
from cronjob_scheduler.scheduler import Scheduler

@pytest.mark.asyncio
async def test_scheduler_registers_job():
    """Test that scheduler correctly registers a new job."""
    # Arrange
    scheduler = Scheduler()
    job = Job(
        container_id="test123",
        container_name="test-container",
        command="echo hello",
        rrule="FREQ=MINUTELY;INTERVAL=5",
    )

    # Act
    await scheduler.register_job(job)

    # Assert
    assert len(scheduler._jobs) == 1
    assert scheduler._jobs[0].container_id == "test123"
```

**Testing best practices:**
- Use descriptive test names that explain what is being tested
- Mock external dependencies (Docker API, time, etc.)
- Test edge cases and error conditions
- Keep tests focused and independent
- Use `pytest.mark.asyncio` for async tests

### Code Coverage

We track code coverage with Codecov. Aim for:
- **Project**: Maintain or improve existing coverage
- **New code**: Minimum 80% coverage for new features

View coverage locally:
```bash
uv run pytest --cov=cronjob_scheduler --cov-report=html
open htmlcov/index.html  # macOS
```

---

## Code Quality

### All Checks

Run all quality checks before committing:

```bash
make check  # Runs: lint, format-check, typecheck, typos
```

### Individual Checks

**Linting with ruff:**
```bash
make lint           # Check for issues
make lint-fix       # Auto-fix issues
```

**Formatting with ruff:**
```bash
make format         # Format code
make format-check   # Check without changing
```

**Type checking with pyright:**
```bash
make typecheck
```

**Spell checking:**
```bash
make typos          # Check for typos
make typos-fix      # Fix typos automatically
```

### Code Style Guidelines

**General:**
- Use Python type hints for all function signatures
- Write docstrings for public functions (Google style)
- Keep functions focused and small (<50 lines)
- Prefer explicit over implicit
- Use descriptive variable names

**Async code:**
- Always use `async def` for async functions
- Use `asyncio.create_task()` for fire-and-forget tasks
- Properly handle cancellation and cleanup

**Good example:**
```python
async def execute_job(job: Job, docker_client: aiodocker.Docker) -> int:
    """Execute a job command in its target container.

    Args:
        job: The job to execute.
        docker_client: Docker API client.

    Returns:
        Exit code (0 for success, -1 for error).
    """
    try:
        container = await docker_client.containers.get(job.container_id)
        exec_instance = await container.exec(["sh", "-c", job.command])
        result = await exec_instance.start()
        return result["ExitCode"]
    except aiodocker.DockerError as e:
        logger.error("Failed to execute job: %s", e)
        return -1
```

**Bad example:**
```python
async def exec(j, d):  # ❌ No docstring, unclear names, no types
    c = await d.containers.get(j.container_id)
    r = await (await c.exec(["sh", "-c", j.command])).start()
    return r["ExitCode"]
```

### Ruff Configuration

The project uses extensive ruff rules for code quality:
- **ASYNC**: Async/await best practices
- **PERF**: Performance anti-patterns
- **G/LOG**: Logging best practices
- **D**: Docstring conventions (Google style)
- And many more - see [pyproject.toml](pyproject.toml)

Some rules are intentionally disabled (see `ignore` list in config).

---

## Git Conventions

### Commit Message Format

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <subject>

<optional body>

<optional footer>
```

**Commit Types:**
- `feat`: New feature or functionality
- `fix`: Bug fix
- `docs`: Documentation only changes
- `chore`: Maintenance (dependencies, configs, build)
- `refactor`: Code changes that neither fix bugs nor add features
- `test`: Adding or updating tests
- `ci`: CI/CD configuration changes
- `perf`: Performance improvements
- `security`: Security fixes or improvements

**Good Examples:**
```bash
feat(scheduler): add support for timezone-aware schedules
fix(docker_watcher): handle race condition on container removal
docs: update CLAUDE.md with development guidelines
chore(deps): bump aiodocker from 0.23.0 to 0.24.0
refactor(models): simplify RRULE parsing logic
test(executor): add test for command timeout handling
ci: add path filtering to GitHub Actions workflow
perf(scheduler): optimize job lookup with dict instead of list
security: migrate to Alpine Linux to reduce CVEs
```

**Bad Examples:**
```bash
update stuff                    # ❌ Too vague, no type
Fixed bug                       # ❌ No type prefix, unclear
Add new feature to scheduler    # ❌ No type prefix
WIP                            # ❌ Not descriptive
asdf                           # ❌ Meaningless
```

### Branch Naming

Use descriptive names with type prefixes matching commit types:

```
<type>/<description-in-kebab-case>
```

**Examples:**
- `feat/add-timezone-support`
- `fix/container-race-condition`
- `docs/add-development-guidelines`
- `chore/update-python-deps`
- `refactor/simplify-rrule-parser`
- `test/add-e2e-tests`
- `security/fix-cve-2024-xxxx`

**Special branches:**
- `main` - Production-ready code (protected)
- `security/*` - Security-related fixes (high priority)

### Pull Request Guidelines

1. **Title**: Use conventional commit format
   ```
   feat(scheduler): add support for cron syntax fallback
   ```

2. **Description**: Include:
   - Summary of changes (what and why)
   - Test plan or how to verify
   - Screenshots/logs if applicable
   - Link to related issues (`Fixes #123`)

3. **Before submitting**:
   - ✅ All tests pass locally
   - ✅ Code is linted and formatted
   - ✅ Documentation is updated
   - ✅ CHANGELOG.md is updated (add to Unreleased section)
   - ✅ Commit messages follow conventions
   - ✅ Branch is up to date with main

4. **PR Size**: Keep PRs focused and reasonably sized
   - Ideal: < 400 lines changed
   - Maximum: < 1000 lines changed
   - Split large features into multiple PRs

5. **Review process**:
   - Address review feedback promptly
   - Push fixes as new commits (don't force-push)
   - Squash commits after approval if needed

---

## Manual Testing

### Local Docker Testing

```bash
# Start scheduler with example containers
make dev

# View logs in real-time
make logs

# Check specific container logs
docker compose logs -f scheduler

# Stop everything
make down
```

### Creating Test Containers

Add a test container to `docker-compose.yml`:

```yaml
test-worker:
  image: alpine:latest
  labels:
    cronjob: |
      FREQ=MINUTELY;INTERVAL=1 => date >> /tmp/test.log
      FREQ=MINUTELY;INTERVAL=2 => echo "Hello" >> /tmp/hello.log
  command: sleep infinity
```

Verify job execution:

```bash
# Check output from first job
docker compose exec test-worker cat /tmp/test.log

# Check output from second job
docker compose exec test-worker cat /tmp/hello.log

# Watch logs
docker compose exec test-worker tail -f /tmp/test.log
```

### Docker Testing Commands

```bash
# Build and test in Docker
make docker-test

# Run all checks in Docker
make docker-check

# Scan for security vulnerabilities
make security-scan

# Build production image
make build
```

---

## Architecture Overview

Understanding the architecture helps when contributing:

### Core Components

1. **[models.py](src/cronjob_scheduler/models.py)** - Data structures and label parsing
   - `Job`: Dataclass representing a scheduled job
   - `parse_cronjob_label()`: Parses `cronjob` label format
   - `ANCHOR`: Fixed datetime for schedule calculations

2. **[scheduler.py](src/cronjob_scheduler/scheduler.py)** - Event-driven job scheduling
   - `Scheduler`: Manages job registration and timing
   - Uses `asyncio.Event` for efficient wake-ups (no polling!)
   - Calculates next run times using RRULE

3. **[executor.py](src/cronjob_scheduler/executor.py)** - Job execution
   - Executes job commands in target containers using `docker exec`
   - Captures output for logging on failures
   - Returns exit codes

4. **[docker_watcher.py](src/cronjob_scheduler/docker_watcher.py)** - Container monitoring
   - Watches Docker events (start/stop/die/destroy)
   - Syncs jobs from container labels
   - Triggers scheduler updates

5. **[main.py](src/cronjob_scheduler/main.py)** - Application orchestration
   - Main scheduler loop
   - Graceful shutdown handling
   - Logging configuration

### Design Principles

- **Event-driven**: No polling, uses `asyncio.Event` for efficient wake-ups
- **Stateless**: No database, rebuilds state from container labels on startup
- **Fire-and-forget**: Jobs execute concurrently using `asyncio.create_task()`
- **Anchored schedules**: All RRULEs use fixed anchor (2025-01-01) for consistency
- **Graceful degradation**: Continues running even if some jobs fail

### Key Patterns

**Event-driven scheduling:**
```python
# Scheduler wakes up when jobs are due OR when jobs are added/removed
while True:
    due_jobs = await scheduler.wait_for_due_jobs()  # Efficient sleep!
    for job in due_jobs:
        asyncio.create_task(execute_job(job))  # Fire-and-forget
```

**Schedule anchoring:**
```python
# All schedules use same anchor for consistent timing
ANCHOR = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
rrule = dateutil.rrule.rrulestr(job.rrule, dtstart=ANCHOR)
next_run = rrule.after(datetime.now(timezone.utc))
```

---

## Submitting Changes

### Workflow Summary

1. **Create branch**
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make changes**
   - Write code
   - Write tests
   - Update docs if needed

3. **Run checks**
   ```bash
   make check
   make test
   ```

4. **Commit**
   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

5. **Push**
   ```bash
   git push -u origin feat/your-feature-name
   ```

6. **Create PR**
   - Use conventional commit format for title
   - Fill out PR template
   - Link related issues
   - Request review

### First-Time Contributors

Welcome! Here are some good first issues:
- Documentation improvements
- Adding test coverage
- Fixing typos
- Small bug fixes

Look for issues labeled `good first issue` or `help wanted`.

---

## Development Tips

### Debugging

**Enable debug logging:**
```bash
LOG_LEVEL=DEBUG make dev
```

**Use Python debugger:**
```python
import pdb; pdb.set_trace()  # Add breakpoint
```

**Test with mock Docker:**
Use `pytest-mock` to mock Docker API calls during testing.

### Common Issues

**Import errors:**
```bash
# Make sure you're in the project root
make install
```

**Pre-commit hooks failing:**
```bash
# Run fixes manually
make lint-fix
make format
```

**Tests hanging:**
```bash
# Add timeout to pytest
uv run pytest --timeout=5
```

**Docker permission errors:**
```bash
# Make sure Docker daemon is running
docker ps

# Check socket permissions
ls -la /var/run/docker.sock
```

---

## Release Process

This section documents how to create a new release. Only maintainers with write access can perform releases.

### Prerequisites

- Write access to the repository
- GitHub CLI (`gh`) installed and authenticated
- Clean working directory on latest `main` branch

### Release Types

Follow [Semantic Versioning](https://semver.org/):
- **Major (X.0.0)**: Breaking changes (API changes, removed features)
- **Minor (x.Y.0)**: New features, backward compatible
- **Patch (x.y.Z)**: Bug fixes, backward compatible

### Release Workflow

#### 1. Prepare the Release

```bash
# Ensure you're on main with latest changes
git checkout main
git pull

# Decide version number (e.g., 2.1.0)
VERSION="2.1.0"
```

#### 2. Update Version Files

Edit two files:

**`pyproject.toml`:**
```toml
version = "2.1.0"  # Update this line
```

**`CHANGELOG.md`:**
```markdown
## [Unreleased]

## [2.1.0] - 2025-10-13

### Added
- New feature description

### Changed
- Change description

### Fixed
- Bug fix description

### Security
- Security improvement description
```

Don't forget to add the version link at the bottom:
```markdown
[2.1.0]: https://github.com/qodevai/cronjobs/releases/tag/v2.1.0
```

#### 3. Create Release Branch and PR

```bash
# Create release branch
git checkout -b chore/release-v${VERSION}

# Commit changes
git add pyproject.toml CHANGELOG.md
git commit -m "chore: bump version to ${VERSION}

Release version ${VERSION} with the following changes:
- Feature/fix summary here
"

# Push branch
git push -u origin chore/release-v${VERSION}

# Create PR
gh pr create --title "chore: release v${VERSION}" --body "## Summary
- Bump version to ${VERSION} in pyproject.toml
- Update CHANGELOG.md with release notes

## Changes
[Describe major changes here]
"
```

#### 4. Wait for CI and Merge

```bash
# Wait for CI to pass, then merge (use PR number from previous command)
gh pr merge <PR_NUMBER> --squash --delete-branch
```

#### 5. Create and Push Git Tag

```bash
# Switch back to main and pull the merge
git checkout main
git pull

# Create and push the version tag
git tag v${VERSION}
git push origin v${VERSION}
```

**Important**: Due to branch protection rules, you **cannot** push directly to main. You **must** create a PR, even for version bumps.

#### 6. Verify Docker Publish

The `docker-publish.yml` workflow will automatically trigger when the tag is pushed:

```bash
# Watch the workflow
gh run list --workflow=docker-publish.yml --limit 1
gh run watch <RUN_ID>

# Verify success
gh run view <RUN_ID>
```

The workflow will publish these images to Docker Hub:
- `qodev/cronjobs:2.1.0` (full version)
- `qodev/cronjobs:2.1` (minor version)
- `qodev/cronjobs:2` (major version)
- `qodev/cronjobs:latest` (only for releases from main)
- `qodev/cronjobs:main` (only for pushes to main)

Both `linux/amd64` and `linux/arm64` platforms are built and published.

#### 7. Create GitHub Release

```bash
# Extract changelog section for this version
gh release create v${VERSION} \
  --title "v${VERSION}" \
  --notes-file <(sed -n "/## \[${VERSION}\]/,/## \[/p" CHANGELOG.md | head -n -1)
```

### Quick Release Checklist

Use this checklist when performing a release:

- [ ] Decide version number (MAJOR.MINOR.PATCH)
- [ ] Update `pyproject.toml` version
- [ ] Update `CHANGELOG.md` with release notes and date
- [ ] Add version link to bottom of CHANGELOG.md
- [ ] Create branch: `chore/release-vX.Y.Z`
- [ ] Commit with conventional commit message
- [ ] Push branch and create PR
- [ ] Wait for CI to pass
- [ ] Merge PR using squash merge
- [ ] Pull latest main
- [ ] Create tag: `git tag vX.Y.Z`
- [ ] Push tag: `git push origin vX.Y.Z`
- [ ] Verify Docker publish workflow succeeds
- [ ] Create GitHub release with changelog

### Troubleshooting Releases

**Tag already exists:**
```bash
# Delete local tag
git tag -d v${VERSION}

# Delete remote tag (be careful!)
git push --delete origin v${VERSION}

# Recreate and push
git tag v${VERSION}
git push origin v${VERSION}
```

**Need to update an existing tag:**
```bash
# Delete old tag locally and remotely
git tag -d v${VERSION}
git push --delete origin v${VERSION}

# Create new tag pointing to correct commit
git tag v${VERSION} <commit-hash>

# Force push the updated tag
git push --force origin v${VERSION}
```

**Docker publish failed:**
- Check GitHub Actions logs: `gh run view <RUN_ID> --log`
- Verify Docker Hub credentials are configured in repository secrets
- Re-trigger workflow: Delete and recreate the tag

**Branch protection blocks direct push:**
- This is expected! Always use PRs, even for version bumps
- Never bypass branch protection for releases

### Post-Release

After a successful release:
1. Announce on relevant channels (if applicable)
2. Close any related milestone on GitHub
3. Update documentation if API changes were made
4. Monitor for issues related to the new release

---

## Resources

- **Documentation**: [README.md](README.md)
- **Development Guide**: [CLAUDE.md](CLAUDE.md)
- **Security**: [SECURITY.md](SECURITY.md)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)
- **Issues**: [GitHub Issues](https://github.com/qodevai/cronjobs/issues)
- **Discussions**: [GitHub Discussions](https://github.com/qodevai/cronjobs/discussions)

---

## Questions?

- 💬 Open a [GitHub Discussion](https://github.com/qodevai/cronjobs/discussions) for general questions
- 🐛 Open an [Issue](https://github.com/qodevai/cronjobs/issues) for bug reports
- 💡 Open an [Issue](https://github.com/qodevai/cronjobs/issues) to discuss feature ideas before implementing

We appreciate all contributions, big and small! 🎉
