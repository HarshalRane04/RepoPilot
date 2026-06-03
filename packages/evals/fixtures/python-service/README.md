# RepoPilot Python Service Fixture

This fixture repository is used by the local RepoPilot benchmark suite. It is intentionally small but executable: tests import the API route and service modules that benchmark tasks expect agents to inspect, modify, or protect.

## Quickstart

```bash
python -m pytest tests
```

Runtime configuration uses `DATABASE_URL`; older `DB_URL` references should be treated as documentation bugs.

