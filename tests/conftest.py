"""
Shared pytest fixtures for Garmin MCP testing

Uses mock Context and patches get_client to return mock Garmin client.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP


@pytest.fixture
def mock_garmin_client():
    """Create a mock Garmin client with common methods stubbed"""
    client = Mock()

    # Configure mock to have all the methods we need
    client.display_name = "TestUser"
    client.get_full_name = Mock(return_value="Test User")
    client.get_activities = Mock(return_value=[])
    client.get_activities_by_date = Mock(return_value=[])
    client.get_activities_fordate = Mock(return_value={})
    client.get_activity = Mock(return_value={})
    client.get_activity_splits = Mock(return_value={})
    client.get_activity_typed_splits = Mock(return_value={})
    client.get_activity_split_summaries = Mock(return_value={})
    client.get_activity_weather = Mock(return_value={})
    client.get_activity_hr_in_timezones = Mock(return_value={})
    client.get_activity_gear = Mock(return_value={})
    client.get_activity_exercise_sets = Mock(return_value={})
    client.count_activities = Mock(return_value=0)
    client.get_activity_types = Mock(return_value=[])
    client.get_stats = Mock(return_value={})
    client.get_user_summary = Mock(return_value={})
    client.get_body_composition = Mock(return_value={})
    client.get_stats_and_body = Mock(return_value={})
    client.get_steps_data = Mock(return_value={})
    client.get_daily_steps = Mock(return_value={})
    client.get_training_readiness = Mock(return_value={})
    client.get_body_battery = Mock(return_value={})
    client.get_body_battery_events = Mock(return_value={})
    client.get_blood_pressure = Mock(return_value={})
    client.get_floors = Mock(return_value={})
    client.get_training_status = Mock(return_value={})
    client.get_rhr_day = Mock(return_value={})
    client.get_heart_rates = Mock(return_value={})
    client.get_hydration_data = Mock(return_value={})
    client.get_sleep_data = Mock(return_value={})
    client.get_stress_data = Mock(return_value={})
    client.get_respiration_data = Mock(return_value={})
    client.get_spo2_data = Mock(return_value={})
    client.get_hrv_data = Mock(return_value={})
    client.get_all_day_stress = Mock(return_value={})
    client.get_all_day_events = Mock(return_value={})
    client.get_goals = Mock(return_value=[])
    client.get_personal_record = Mock(return_value=[])
    client.get_earned_badges = Mock(return_value=[])
    client.get_badge_challenges = Mock(return_value=[])
    client.get_adhoc_challenges = Mock(return_value=[])
    client.get_race_predictions = Mock(return_value={})
    client.get_devices = Mock(return_value=[])
    client.get_device_last_used = Mock(return_value={})
    client.get_device_settings = Mock(return_value={})
    client.get_device_alarms = Mock(return_value=[])
    client.get_gear = Mock(return_value=[])
    client.get_gear_stats = Mock(return_value={})
    client.add_gear_to_activity = Mock()
    client.remove_gear_from_activity = Mock()
    client.get_weigh_ins = Mock(return_value={})
    client.add_weigh_in = Mock()
    client.delete_weigh_ins = Mock(return_value=0)
    client.get_user_profile = Mock(return_value={})
    client.get_userprofile_settings = Mock(return_value={})
    client.get_unit_system = Mock(return_value="metric")
    client.get_workouts = Mock(return_value=[])
    client.get_workout_by_id = Mock(return_value={})
    client.query_garmin_graphql = Mock(return_value={})
    client.upload_workout = Mock(return_value={})
    client.get_endurance_score = Mock(return_value={})
    client.get_hill_score = Mock(return_value={})
    client.get_fitnessage_data = Mock(return_value={})
    client.get_lactate_threshold = Mock(return_value={})
    client.get_progress_summary_between_dates = Mock(return_value={})
    client.get_pregnancy_summary = Mock(return_value={})
    client.get_menstrual_data_for_date = Mock(return_value={})
    client.get_menstrual_calendar_data = Mock(return_value={})
    client.add_body_composition = Mock(return_value={})
    client.set_blood_pressure = Mock(return_value={})
    client.add_hydration_data = Mock(return_value={})
    client.garth = Mock()
    client.garth.post = Mock()
    client.garth.get = Mock()

    return client


@pytest.fixture
def mock_context():
    """Create a mock FastMCP Context"""
    ctx = Mock()
    ctx.get_state = AsyncMock(return_value="mock_tokens")
    ctx.set_state = AsyncMock()
    ctx.delete_state = AsyncMock()
    return ctx


@pytest.fixture
def patched_get_client(mock_garmin_client):
    """Patch get_client to return mock Garmin client"""
    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.client_factory.get_client", mock_get_client):
        yield mock_garmin_client


@pytest.fixture
def today_str():
    """Return today's date as YYYY-MM-DD string"""
    return datetime.now().strftime("%Y-%m-%d")


@pytest.fixture
def yesterday_str():
    """Return yesterday's date as YYYY-MM-DD string"""
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


@pytest.fixture
def date_range():
    """Return a tuple of (start_date, end_date) as strings"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    return (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))


@pytest.fixture
def sample_activity():
    """Sample activity data matching Garmin API response format"""
    return {
        "activityId": 12345678901,
        "activityName": "Morning Run",
        "activityType": {
            "typeKey": "running",
            "typeId": 1
        },
        "startTimeLocal": "2024-01-15 07:00:00",
        "distance": 5000.0,
        "duration": 1800.0,
        "averageHR": 145,
        "maxHR": 165,
        "calories": 350
    }


@pytest.fixture
def sample_steps_data():
    """Sample steps data matching Garmin API response format"""
    return {
        "steps": 10000,
        "dailyStepGoal": 8000,
        "stepGoalDistance": 10000,
        "totalDistance": 7500,
        "wellnessDistanceUnit": "meter"
    }


@pytest.fixture
def sample_sleep_data():
    """Sample sleep data matching Garmin API response format"""
    return {
        "dailySleepDTO": {
            "sleepTimeSeconds": 28800,  # 8 hours
            "napTimeSeconds": 0,
            "sleepStartTimestampGMT": 1705276800000,
            "sleepEndTimestampGMT": 1705305600000,
            "deepSleepSeconds": 7200,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 7200,
            "awakeSleepSeconds": 0,
            "awakeCount": 2,
            "restlessMomentsCount": 15,
            "avgSleepStress": 15,
            "restingHeartRate": 55,
            "sleepScores": {
                "overall": {
                    "value": 85,
                    "qualifierKey": "GOOD",
                    "optimalStart": 75,
                    "optimalEnd": 100
                }
            }
        },
        "wellnessSpO2SleepSummaryDTO": {
            "averageSpo2": 96,
            "lowestSpo2": 93
        },
        "avgOvernightHrv": 45
    }


@pytest.fixture
def sample_heart_rate_data():
    """Sample heart rate data matching Garmin API response format"""
    return {
        "restingHeartRate": 55,
        "maxHeartRate": 180,
        "minHeartRate": 45,
        "lastSevenDaysAvgRestingHeartRate": 57
    }


@pytest.fixture
def sample_body_battery_data():
    """Sample body battery data matching Garmin API response format"""
    return [{
        "startTimestampGMT": 1705276800000,
        "endTimestampGMT": 1705363200000,
        "chargedValue": 100,
        "drainedValue": 25,
        "bodyBatteryMostRecentValue": 75
    }]


@pytest.fixture
def sample_training_status():
    """Sample training status data matching Garmin API response format"""
    return {
        "trainingStatusKey": "PRODUCTIVE",
        "load7Day": 250,
        "load4Week": 1000,
        "vo2MaxValue": 52.5,
        "fitnessAge": 25
    }


def create_test_app(module):
    """
    Helper function to create a FastMCP app with a specific module registered

    Args:
        module: The module to register (e.g., health_wellness)

    Returns:
        FastMCP app instance with tools registered
    """
    app = FastMCP("Test Garmin MCP")
    app = module.register_tools(app)
    return app


@pytest.fixture
def app_factory():
    """
    Factory fixture to create FastMCP apps with different modules

    Usage:
        app = app_factory(health_wellness)
    """
    def _create_app(module):
        return create_test_app(module)

    return _create_app
