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

## Garmin Workout API Requirements

The `workouts.py` module includes normalization functions that transform workout data to match Garmin's API requirements. Key requirements:

### Step Structure
- **`stepId`**: Must be an integer (1, 2, 3...), NOT `null`. API rejects null values.
- **`type`**: Must be `"ExecutableStepDTO"` for regular steps, `"RepeatGroupDTO"` for repeats. NOT `"WorkoutStep"`.

### Step Type IDs (stepTypeId)
The `stepTypeKey` must match the correct `stepTypeId`:
| stepTypeKey | stepTypeId | displayOrder |
|-------------|------------|--------------|
| warmup      | 1          | 1            |
| cooldown    | 2          | 2            |
| interval    | 3          | 3            |
| recovery    | 4          | 4            |
| rest        | 5          | 5            |
| repeat      | 6          | 6            |
| other       | 7          | 7            |

### Common Issues Fixed by Normalization
1. Coach sends `stepId: null` → Normalized to sequential integers
2. Coach sends `type: "WorkoutStep"` → Normalized to `"ExecutableStepDTO"`
3. Incorrect `stepTypeId` values → Normalized based on `stepTypeKey`

### Workout Creation Endpoints
- **Web UI endpoint**: `https://connect.garmin.com/gc-api/workout-service/workout`
- **API endpoint**: `https://connectapi.garmin.com/workout-service/workout`

### Workout Scheduling Constraint
Garmin's API requires workouts to exist in the library before they can be scheduled to the calendar. There is NO way to schedule a workout without it being in the library first. Deleting a workout from the library also cascade-deletes any scheduled calendar entries.

This means `plan_workout` and `schedule_workout_directly` both create workouts in the library AND on the calendar.

The `_normalize_workout_structure()` function handles these transformations automatically.
