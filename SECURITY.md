# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| < 0.1.0 | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability within this project, please send an email to jan.scheffler@qodev.ai. All security vulnerabilities will be promptly addressed.

Please include the following information in your report:
- Type of vulnerability
- Full paths of affected source file(s)
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

## Security Considerations

When deploying this scheduler:

1. **Docker Socket Access**: The scheduler requires read access to `/var/run/docker.sock`. This grants significant privileges. Only run the scheduler in trusted environments.

2. **Container Execution**: The scheduler executes commands in other containers via `docker exec`. Ensure that:
   - Container labels are only set by trusted sources
   - Commands in cronjob labels are reviewed before deployment
   - Containers running scheduled jobs have appropriate security constraints

3. **Network Isolation**: Consider running the scheduler in a separate Docker network with limited access.

4. **Logging**: Enable logging to monitor executed jobs and detect suspicious activity. Set `LOG_LEVEL=DEBUG` to see detailed execution logs.

## Disclosure Policy

When we receive a security vulnerability report, we will:

1. Confirm the problem and determine affected versions
2. Audit code to find similar problems
3. Prepare fixes for all supported versions
4. Release new versions as soon as possible

Thank you for helping keep this project secure!
