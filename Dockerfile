# Use Python 3.12 slim image for smaller size
FROM python:3.12-slim

# Note: .dockerignore is symlinked to .gitignore for unified exclusion rules

# Set working directory
WORKDIR /app

# Install uv for faster dependency management
# https://github.com/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Copy dependency files and README first for better layer caching
COPY pyproject.toml README.md ./

# Copy the application source code (needed for editable install)
COPY src/ ./src/

# Remove local source references from pyproject.toml (not available in Docker)
# and install dependencies using uv
RUN sed -i '/\[tool.uv.sources\]/,$d' pyproject.toml && \
    uv pip install -e .

# Default to HTTP transport
ENV MCP_TRANSPORT=streamable-http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8080

EXPOSE 8080

# Run the MCP server with HTTP transport
CMD ["python", "-m", "garmin_mcp", "--http"]
