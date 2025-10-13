# Contributing to Cronjob Scheduler

## Development Setup

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (for integration testing)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd cronjobs

# Install dependencies (including dev dependencies)
uv sync --all-extras

# Verify installation
uv run pytest
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_scheduler.py

# Run specific test
uv run pytest tests/test_scheduler.py::test_register_job_calculates_next_run

# Run with coverage
uv run pytest --cov=cronjob_scheduler --cov-report=html
```

### Test Structure

- `tests/test_models.py` - Label parsing and Job model
- `tests/test_scheduler.py` - Scheduler logic and timing
- `tests/test_executor.py` - Job execution in containers
- `tests/test_docker_watcher.py` - Container monitoring

### Writing Tests

Follow the TDD approach used in this project:

1. Write test first
2. Run test (should fail)
3. Implement minimal code to pass
4. Refactor if needed
5. Repeat

Example test:

```python
@pytest.mark.asyncio
async def test_new_feature(scheduler):
    """Test description."""
    # Arrange
    job = create_test_job()

    # Act
    scheduler.register_job(job)

    # Assert
    assert len(scheduler._jobs) == 1
```

## Code Style

- Use Python type hints
- Follow PEP 8
- Async functions should be prefixed with `async def`
- Keep functions focused and small
- Add docstrings to public functions

## Git Conventions

### Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <subject>
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

**Good Examples:**
```bash
feat(scheduler): add support for timezone-aware schedules
fix(docker_watcher): handle race condition on container removal
docs: update CLAUDE.md with development guidelines
chore(deps): bump aiodocker from 0.23.0 to 0.24.0
refactor(models): simplify RRULE parsing logic
test(executor): add test for command timeout handling
ci: integrate Docker Scout vulnerability scanning
```

**Bad Examples:**
```bash
update stuff                    # Too vague
Fixed bug                       # No type prefix, no description
Add new feature to scheduler    # No type prefix
WIP                            # Not descriptive
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

### Workflow

1. **Create branch**: `git checkout -b feat/your-feature-name`
2. **Make changes**: Write code and tests
3. **Run quality checks**:
   ```bash
   uv run ruff check
   uv run ruff format
   uv run pyright
   uv run pytest
   ```
4. **Commit**: `git commit -m "feat(scope): description"`
5. **Push**: `git push -u origin feat/your-feature-name`
6. **Create PR**: Use conventional commit format for PR title

## Manual Testing

### Local Docker Testing

```bash
# Build and run
docker-compose up --build

# Check logs
docker-compose logs -f scheduler

# Test health check
curl http://localhost:8080/health

# Stop
docker-compose down
```

### Creating Test Containers

Add a test container to `docker-compose.yml`:

```yaml
test-worker:
  image: alpine:latest
  labels:
    cronjob: 'FREQ=MINUTELY;INTERVAL=1 => date >> /tmp/test.log'
  command: sleep infinity
```

Check execution:

```bash
docker exec test-worker cat /tmp/test.log
```

## Architecture

### Key Components

1. **models.py**: Data models and label parsing
2. **scheduler.py**: Event-driven job scheduling
3. **executor.py**: Docker exec wrapper
4. **docker_watcher.py**: Container event monitoring
5. **main.py**: Application orchestration

### Design Principles

- **Event-driven**: No polling, use asyncio.Event for wake-ups
- **Stateless**: No persistent storage, rebuild from container labels
- **Concurrent**: Use asyncio.create_task for fire-and-forget execution
- **Anchored schedules**: All RRULEs use fixed anchor for consistency

## Submitting Changes

1. Create a feature branch
2. Write tests for new functionality
3. Ensure all tests pass
4. Update documentation if needed
5. Submit pull request

## Questions?

Open an issue for discussion before starting major changes.
