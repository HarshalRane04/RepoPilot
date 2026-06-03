FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pytest ruff mypy

WORKDIR /workspace

CMD ["python", "--version"]
