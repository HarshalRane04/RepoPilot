FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pytest ruff mypy

COPY packages/shared_contracts /opt/repopilot/packages/shared_contracts
COPY packages/policy_engine /opt/repopilot/packages/policy_engine
RUN pip install --no-cache-dir /opt/repopilot/packages/shared_contracts /opt/repopilot/packages/policy_engine
COPY apps/api/requirements.txt /opt/repopilot/api-requirements.txt
RUN sed '/^-e[[:space:]]/d' /opt/repopilot/api-requirements.txt > /tmp/api-requirements.txt \
    && pip install --no-cache-dir -r /tmp/api-requirements.txt \
    && rm /tmp/api-requirements.txt
COPY services/sandbox_runner/server.py /opt/repopilot/server.py

RUN useradd --create-home --uid 10001 sandbox \
    && mkdir -p /workspace /tmp/repopilot-agent-workspaces /run/repopilot-sandbox \
    && chown -R sandbox:sandbox /workspace /tmp/repopilot-agent-workspaces /run/repopilot-sandbox

USER sandbox
WORKDIR /workspace

HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD ["python", "/opt/repopilot/server.py", "--healthcheck"]
CMD ["python", "/opt/repopilot/server.py"]
