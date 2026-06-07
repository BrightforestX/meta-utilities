# Production Docker image for deep-research-mcp
# Supports both stdio (for local agents) and HTTP/Streamable HTTP transports

FROM python:3.12-slim

WORKDIR /app

# Install uv for fast, reproducible installs
RUN pip install --no-cache-dir uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev || uv pip install --system fastmcp openai

# Copy the server code
COPY deep-research-mcp.py ./

# Non-root user for security
RUN useradd -m -u 1000 mcpuser
USER mcpuser

EXPOSE 8000

# Default to stdio for local MCP clients (agents spawn it with -i)
# For remote/HTTP use: docker run ... python deep_research_mcp.py --transport http --host 0.0.0.0 --port 8000
ENTRYPOINT ["python", "deep_research_mcp.py"]
