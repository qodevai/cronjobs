# Quick Start Guide

## Test it in 2 minutes

1. **Start the scheduler and example worker:**

```bash
docker-compose up --build
```

2. **Watch the logs** (in another terminal):

```bash
# See the scheduler logs
docker-compose logs -f scheduler

# See example worker executing jobs
docker exec example-worker sh -c "dmesg | tail -20"
```

3. **Check status:**

```bash
docker logs cronjob-scheduler
```

You should see "Cronjob scheduler starting...".

4. **Add your own job:**

Edit `docker-compose.yml` and add a new service:

```yaml
my-worker:
  image: alpine:latest
  labels:
    ai.qodev.cronjobs: |
      FREQ=MINUTELY;INTERVAL=1 => echo "Hello from my worker! $(date)" >> /tmp/output.log
  command: sleep infinity
```

Restart:

```bash
docker-compose up -d
```

Check the output:

```bash
docker exec my-worker cat /tmp/output.log
```

## RRULE Examples

**Note:** RRULE can be uppercase, lowercase, or mixed case.

### Every 5 minutes
```
FREQ=MINUTELY;INTERVAL=5 => your-command
# or lowercase:
freq=minutely;interval=5 => your-command
```

### Every hour
```
FREQ=HOURLY => your-command
# or lowercase:
freq=hourly => your-command
```

### Daily at 2 AM
```
FREQ=DAILY;BYHOUR=2;BYMINUTE=0 => your-command
```

### Every weekday at 9 AM
```
FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9 => your-command
```

### Every Monday
```
FREQ=WEEKLY;BYDAY=MO => your-command
```

### First day of every month
```
FREQ=MONTHLY;BYMONTHDAY=1 => your-command
```

## Multiple Jobs

Add multiple jobs to one container by using newlines:

```yaml
labels:
  ai.qodev.cronjobs: |
    FREQ=MINUTELY;INTERVAL=5 => python sync.py
    FREQ=HOURLY => python cleanup.py
    FREQ=DAILY;BYHOUR=3 => python backup.py
```

## Debugging

### Check if scheduler detected your container:

The scheduler logs will show when it finds containers with ai.qodev.cronjobs labels.

### Check if job is executing:

Look at the target container's logs:

```bash
docker logs <your-container-name>
```

### Common issues:

1. **Job not running?**
   - Check RRULE syntax
   - Verify container is running: `docker ps`
   - Check scheduler can access docker socket

2. **Command fails?**
   - Test command manually: `docker exec <container> sh -c "your-command"`
   - Check if required binaries exist in container

3. **Scheduler not starting?**
   - Verify docker socket is mounted: `docker inspect cronjob-scheduler`
   - Check logs: `docker logs cronjob-scheduler`

## Development

Run tests:

```bash
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.
