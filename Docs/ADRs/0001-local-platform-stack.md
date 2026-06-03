# ADR-0001: Local Platform Stack

## Status

Accepted

## Context

RepoPilot needs a local runtime that can later support GitHub webhooks, long-running agent jobs, code retrieval, sandboxed execution, telemetry, and a dashboard.

## Decision

Use FastAPI, Next.js, PostgreSQL with pgvector, Redis, Celery, and Docker Compose for the Phase 1 local platform.

## Consequences

This gives the project a production-like shape early while keeping local development approachable. Later phases can harden workers, split services, add object storage, and introduce cloud deployment without changing the core service boundaries.
