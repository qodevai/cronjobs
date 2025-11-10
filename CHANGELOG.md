# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.0] - 2025-11-10

### Added
- Docker healthcheck to verify scheduler process is running
  - Checks every 10s with 10s start period
  - Prevents unhealthy containers from receiving traffic
  - Enables proper dependency ordering in docker-compose
- Enhanced CI/CD pipeline with comprehensive error detection:
  - Added smoke test to verify production Docker image can start
  - Added healthcheck verification to catch crash-looping containers
  - Added job execution verification (line count > 0) to ensure scheduler actually works
  - Fixed e2e test that was passing even when no jobs executed

### Fixed
- Fixed ModuleNotFoundError in production Docker image by using `uv run` to access virtualenv
- Fixed pyright type checking in CI by installing libatomic1 dependency for Node.js
- Fixed e2e test that wasn't actually verifying jobs executed (only checked if file exists)
- Schedule display now shows RRULE syntax instead of unhelpful DTSTART timestamp
- Improved type annotations for `Job.rrule` field (changed from `any` to `RRule | RRuleSet`)

### Changed
- docker-compose now waits for scheduler to be healthy before starting worker containers
- e2e tests now verify container health instead of just checking if it's "Up"

## [2.0.0] - 2025-10-13

### Changed (BREAKING)
- **Changed default label from `cronjob` to `ai.qodev.cronjobs`** for better Docker naming conventions
  - Follows reverse DNS notation as per Docker documentation
  - Label name remains configurable via `WATCH_LABEL` environment variable
  - Users can continue using `cronjob` by setting `WATCH_LABEL=cronjob`

### Added
- Developer experience improvements:
  - Comprehensive Makefile with 15+ commands for common tasks
  - Pre-commit hooks with auto-formatting and linting
  - `make help` command for command discovery
  - Quick setup commands: `make install`, `make check`, `make test`
- Enhanced CI/CD:
  - Added typos workflow for spell checking
  - Enhanced CI with better path filtering and optimizations
  - Codecov integration for test coverage tracking
  - Duration tracking for slow tests (`--durations=10`)
- New formatting utilities module (`formatting.py`):
  - Human-readable duration formatting
  - Next run time calculations with RRULE support
  - Comprehensive test coverage for formatting logic
- Documentation improvements:
  - Added CONTRIBUTING.md with detailed development guidelines
  - Enhanced CLAUDE.md with Alpine migration learnings and git conventions
  - Added pre-commit hook documentation
  - Updated all examples to use new label name

### Changed
- Migrated Docker base image from `python:3.12-slim` to `python:3.12-alpine`
- Reduced Docker image size by ~24 MB (from 75 MB to 51 MB)
- Improved logging output format for better readability
- Enhanced test coverage with new formatting tests

### Security
- Fixed HIGH severity OpenSSL vulnerability (CVE-2025-9230)
- Reduced total vulnerabilities by 88% (from 25 to 3)
- Eliminated all HIGH severity vulnerabilities
- Reduced vulnerable packages from 11 to 2

## [1.0.0] - 2025-10-09

### Added
- Production-ready release
- Multi-stage Docker builds (test/production targets)
- End-to-end testing in CI pipeline
- Comprehensive test coverage (71%)
- Docker-based CI/CD running Python 3.12

### Changed
- Python version fixed to 3.12 (matching Docker image)
- CI now runs all tests in Docker containers
- Optimized production Docker image (200MB)
- Updated documentation and badges

### Fixed
- README.md encoding issues (removed Unicode tree characters)
- PLR0912 linting issue in executor.py
- Coverage extraction in CI workflow

## [0.1.0] - 2025-10-09

### Added
- Initial release of Docker-native cronjob scheduler
- RRULE-based scheduling (RFC 5545 recurrence rules)
- Event-driven container monitoring via Docker API
- Concurrent job execution using asyncio
- Support for multiple jobs per container
- Case-insensitive RRULE parsing (uppercase/lowercase/mixed)
- Comprehensive test suite with pytest
- GitHub Actions CI/CD pipeline
- Docker Hub multi-arch publishing (amd64/arm64)
- Complete documentation (README, CONTRIBUTING, SECURITY, QUICKSTART)
- Example configurations and docker-compose files
- Configurable logging levels (DEBUG, INFO, WARNING, ERROR)
- Graceful shutdown handling (SIGTERM/SIGINT)

### Features
- Stateless design - no persistent storage required
- Fire-and-forget job execution
- Automatic schedule anchoring for consistent timing
- Docker socket read-only access
- Minimal dependencies (aiodocker, python-dateutil)

[2.1.0]: https://github.com/qodevai/cronjobs/releases/tag/v2.1.0
[2.0.0]: https://github.com/qodevai/cronjobs/releases/tag/v2.0.0
[1.0.0]: https://github.com/qodevai/cronjobs/releases/tag/v1.0.0
[0.1.0]: https://github.com/qodevai/cronjobs/releases/tag/v0.1.0
