# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/qodevai/cronjobs/releases/tag/v1.0.0
[0.1.0]: https://github.com/qodevai/cronjobs/releases/tag/v0.1.0
