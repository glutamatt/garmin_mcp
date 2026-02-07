# Use Python 3.12 slim image for smaller size
FROM python:3.12-slim

# Note: Build context must be ./mcp-servers (not ./mcp-servers/garmin_mcp)
# to access the python-garminconnect submodule as a sibling directory.

# Set working directory
WORKDIR /app

# Install uv for faster dependency management
# https://github.com/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Copy python-garminconnect submodule (sibling directory)
COPY python-garminconnect /app/python-garminconnect

# Copy dependency files and README first for better layer caching
COPY garmin_mcp/pyproject.toml garmin_mcp/README.md ./

# Copy the application source code (needed for editable install)
COPY garmin_mcp/src/ ./src/

# Install dependencies using uv (strip uv.sources, use local path directly)
RUN sed -i '/\[tool.uv.sources\]/,$d' pyproject.toml && \
    uv pip install /app/python-garminconnect && \
    uv pip install .

# Copy test files (optional, for testing in container)
COPY garmin_mcp/tests/ ./tests/
COPY garmin_mcp/pytest.ini ./

# Create directory for Garmin tokens
RUN mkdir -p /root/.garminconnect && \
    chmod 700 /root/.garminconnect

# Default to HTTP transport
ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8080

EXPOSE 8080

# Run the MCP server with HTTP transport
CMD ["python", "-m", "garmin_mcp", "--http"]
