# Use Python 3.12 slim image for smaller size
FROM python:3.12-slim

# Note: .dockerignore is symlinked to .gitignore for unified exclusion rules

# Install git for cloning dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv for faster dependency management
# https://github.com/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Clone python-garminconnect library (with latest calendar/coaching features)
# Using forked branch with calendar management functions (get_scheduled_workouts_for_range, get_calendar_items_for_range)
RUN git clone --depth 1 --branch feature/add-coaching-endpoints https://github.com/glutamatt/python-garminconnect.git /tmp/garminconnect

# Copy dependency files and README first for better layer caching
COPY pyproject.toml README.md ./

# Copy the application source code (needed for editable install)
COPY src/ ./src/

# Remove local source references from pyproject.toml and update to use /tmp/garminconnect
RUN sed -i '/\[tool.uv.sources\]/,$d' pyproject.toml

# Install garminconnect from local copy (includes calendar events and coaching endpoints)
RUN uv pip install -e /tmp/garminconnect

# Install garmin-mcp with remaining dependencies
RUN uv pip install -e .

# Create data directory for session storage
RUN mkdir -p /data/garmin_sessions

# Default to HTTP transport
ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8080

EXPOSE 8080

# Run the MCP server with HTTP transport
CMD ["python", "-m", "garmin_mcp", "--http"]
