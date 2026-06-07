FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY batch_orchestrator/ batch_orchestrator/

RUN pip install --no-cache-dir .

ENV BATCH_ORCHESTRATOR_HOME=/data
VOLUME ["/data"]

ENTRYPOINT ["batch-orchestrator-mcp"]
