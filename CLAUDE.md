# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Garmin MCP Server - A Model Context Protocol (MCP) server that connects to Garmin Connect and exposes fitness/health data to Claude and other MCP-compatible clients. Uses the [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) library.

## Development Commands

```bash
# Install dependencies
uv sync

# Run the MCP server
GARMIN_EMAIL=your@email.com GARMIN_PASSWORD=yourpass uv run garmin-mcp

# Run integration tests (mocked Garmin API, no credentials needed)
uv run pytest tests/integration/

# Run specific test module
uv run pytest tests/integration/test_health_wellness_tools.py -v

# Run e2e tests (requires real Garmin credentials)
uv run pytest tests/e2e/ -m e2e -v

# Test with MCP Inspector
npx @modelcontextprotocol/inspector uv run garmin-mcp
```

## Architecture

### Module Pattern
Each module in `src/garmin_mcp/` follows the same pattern:
- `configure(client)` - Sets the global Garmin client instance
- `register_tools(app)` - Registers MCP tools using `@app.tool()` decorators
- All tools are async and return JSON strings via `json.dumps()`

### Entry Point (`src/garmin_mcp/__init__.py`)
- `main()` initializes Garmin client and MCP server
- `init_api()` handles OAuth authentication with token persistence
- Supports MFA (multi-factor authentication)

### Modules by Domain
- `activity_management.py` - Activity listing, details, splits
- `health_wellness.py` - Health metrics (steps, heart rate, sleep, stress)
- `training.py` - Training status, readiness, VO2max
- `workouts.py` - Workout management
- `challenges.py`, `devices.py`, `gear_management.py`, `user_profile.py`, `weight_management.py`, `womens_health.py`, `data_management.py`

## Testing

- **Integration tests** (`tests/integration/`): 96 tests using mocked Garmin API responses
- **E2E tests** (`tests/e2e/`): 4 tests requiring real credentials, skipped by default
- Mock fixtures in `tests/fixtures/garmin_responses.py`
- Shared fixtures in `tests/conftest.py`

## Environment Variables

- `GARMIN_EMAIL` / `GARMIN_PASSWORD` - Garmin Connect credentials
- `GARMIN_EMAIL_FILE` / `GARMIN_PASSWORD_FILE` - File-based alternatives
- `GARMINTOKENS` - Token storage directory (default: `~/.garminconnect`)
