# Webhook Ingestion Service

Status: scaffold only. This is a planned extraction boundary, not a separate deployable service in v1.

Runtime implementation currently lives in `apps/api/app/services/github_webhooks.py`, `apps/api/app/services/github_ingestion.py`, and `apps/api/app/worker/tasks.py`; this directory is reserved for future extraction of webhook intake workers.

Phase 2 owns GitHub webhook verification, delivery dedupe, normalization, event persistence, and queue dispatch.
