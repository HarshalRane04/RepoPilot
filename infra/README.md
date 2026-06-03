# Infrastructure

Status: infrastructure scaffold. The current source of truth is root `docker-compose.yml`; this directory is reserved for future deployment references such as Terraform, cloud runbooks, observability collectors, and sandbox runner pools.

Phase 1 uses the root `docker-compose.yml` as the local source of truth.

The local stack contains:

- `api`: FastAPI application.
- `worker`: Celery worker using the same backend image.
- `web`: Next.js dashboard shell.
- `postgres`: PostgreSQL 16 with pgvector.
- `redis`: queue/cache backbone.

Cloud deployment, Terraform, object storage, observability collectors, and sandbox runner pool hardening belong to later phases after the secure issue-to-PR loop exists.
