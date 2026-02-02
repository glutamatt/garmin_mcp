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
4. Zone-based targets: Coach sends `targetValueOne: 1, targetValueTwo: 1` → Normalized to `zoneNumber: 1`

### Zone-Based Target Types
For heart rate and power zone targets, Garmin expects `zoneNumber` field (1-5 for HR, 1-7 for power), NOT `targetValueOne`/`targetValueTwo`:

```json
// WRONG (what coaches often send)
"targetType": {"workoutTargetTypeKey": "heart.rate.zone"},
"targetValueOne": 1,
"targetValueTwo": 1

// CORRECT (what Garmin expects)
"targetType": {"workoutTargetTypeKey": "heart.rate.zone"},
"zoneNumber": 1,
"targetValueOne": null,
"targetValueTwo": null
```

The normalization auto-detects when `targetValueOne == targetValueTwo` (1-5) and converts to `zoneNumber`.

### Workout Creation Endpoints
- **Web UI endpoint**: `https://connect.garmin.com/gc-api/workout-service/workout`
- **API endpoint**: `https://connectapi.garmin.com/workout-service/workout`

### Workout Scheduling Constraint
Garmin's API requires workouts to exist in the library before they can be scheduled to the calendar. There is NO way to schedule a workout without it being in the library first. Deleting a workout from the library also cascade-deletes any scheduled calendar entries.

This means `plan_workout` creates workouts in the library AND on the calendar.

The `_normalize_workout_structure()` function handles these transformations automatically.

## Workouts Module Tool Reference

The `workouts.py` module provides 17 tools organized into 4 groups:

### Workout Library (CRUD)
| Tool | Description |
|------|-------------|
| `get_workouts` | List all workouts in library |
| `get_workout` | Get workout details by ID |
| `create_workout` | Create workout without scheduling |
| `update_workout` | Modify existing workout |
| `delete_workout` | Remove workout (cascade deletes calendar entries) |
| `download_workout` | Export workout as FIT file |

### Scheduling
| Tool | Description |
|------|-------------|
| `plan_workout` | Create AND schedule in one step (RECOMMENDED) |
| `schedule_workout` | Schedule existing workout to calendar |
| `reschedule_workout` | Move scheduled workout to new date |
| `unschedule_workout` | Remove from calendar (keeps in library) |
| `get_scheduled_workouts` | List scheduled workouts in date range |
| `get_calendar` | Full calendar view (RECOMMENDED for overview) |

### Training Plans
| Tool | Description |
|------|-------------|
| `get_training_plan` | Get plan workouts for a date |
| `get_adaptive_plan` | Full adaptive plan with phases |
| `get_adaptive_workout` | Detailed adaptive workout structure |
| `get_coaching_preferences` | User's training day preferences |

### Analytics
| Tool | Description |
|------|-------------|
| `get_readiness` | Training readiness/recovery (CHECK BEFORE PLANNING) |
| `get_compliance` | Workout completion tracking |
| `get_weekly_summary` | Weekly training review |

### Deprecated Aliases (Backward Compatibility)
The following old tool names still work but will be removed in v2.0:
- `get_workout_by_id` → `get_workout`
- `upload_workout` → `create_workout`
- `delete_workout_from_library` → `delete_workout`
- `update_workout_in_library` → `update_workout`
- `cancel_scheduled_workout` → `unschedule_workout`
- `get_training_calendar` → `get_calendar`
- `get_adaptive_training_plan_full` → `get_adaptive_plan`
- `get_fbt_adaptive_workout_details` → `get_adaptive_workout`
- `get_adaptive_coaching_preferences` → `get_coaching_preferences`
- `get_training_plan_workouts` → `get_training_plan`
- `get_workout_compliance` → `get_compliance`
- `get_athlete_readiness` → `get_readiness`
- `get_weekly_training_summary` → `get_weekly_summary`
