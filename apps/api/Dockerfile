FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/apps/api:/app/packages/shared_contracts:/app/packages/evals:/app/packages/policy_engine:/app/packages/llm_client:/app/packages/github_client

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

COPY packages/shared_contracts ./packages/shared_contracts
COPY packages/evals ./packages/evals
COPY packages/policy_engine ./packages/policy_engine
COPY packages/llm_client ./packages/llm_client
COPY packages/github_client ./packages/github_client
COPY apps/api/requirements.txt ./apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt

COPY apps/api ./apps/api

WORKDIR /app/apps/api

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
