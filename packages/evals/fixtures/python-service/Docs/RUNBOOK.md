# Python Service Runbook

## Local Services

Start dependencies before running tests:

```bash
docker compose up postgres redis
```

## Approval Workflow

Plans must be approved before implementation tools can write to an isolated workspace. Rejected or revised plans must be recorded with a reason.

