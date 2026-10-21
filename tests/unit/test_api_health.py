"""Unit tests for garmin_mcp.api.health — curation logic with mock client."""

import pytest
from unittest.mock import Mock
from garmin_mcp.api import health as api
from garmin_mcp.api.contract import AuthError, RateLimited
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


@pytest.fixture
def client():
    return Mock()


NO_DATA_DAY = {"date": "2024-01-15", "available": False, "reason": "no_data"}


# ── get_sleep ────────────────────────────────────────────────────────────────


class TestGetSleep:
    def test_curates_correctly(self, client):
        client.get_sleep_data.return_value = {
            "dailySleepDTO": {
                "sleepTimeSeconds": 28800,
                "deepSleepSeconds": 7200,
                "lightSleepSeconds": 14400,
                "remSleepSeconds": 7200,
                "awakeSleepSeconds": 0,
                "avgSleepStress": 15,
                "calendarDate": "2024-01-15",
                "sleepStartTimestampLocal": 1705274400000,
                "sleepEndTimestampLocal": 1705303200000,
                "sleepNeed": {"actual": 480, "feedback": "NO_CHANGE"},
                "sleepScores": {"overall": {"value": 85, "qualifierKey": "GOOD"},
                                "deepPercentage": {"value": 25, "qualifierKey": "EXCELLENT"}},
            },
            # Garmin: the resting HR at the top level, the SpO2 in its own summary
            "restingHeartRate": 55,
            "wellnessSpO2SleepSummaryDTO": {"averageSPO2": 96, "lowestSPO2": 93},
            "avgOvernightHrv": 45,
            "hrvStatus": "BALANCED",
        }
        result = api.get_sleep(client, "2024-01-15")
        assert result["date"] == "2024-01-15"
        assert result["sleep_score"] == 85
        assert result["sleep_score_factors"] == {"deep": "EXCELLENT"}
        assert result["sleep_s"] == 28800
        assert result["deep_sleep_s"] == 7200
        assert (result["bedtime"], result["wake_time"]) == ("2024-01-14T23:20:00", "2024-01-15T07:20:00")
        assert result["sleep_need_s"] == 28800
        assert result["resting_hr_bpm"] == 55
        assert (result["avg_sleep_spo2_percent"], result["lowest_sleep_spo2_percent"]) == (96, 93)
        assert result["avg_overnight_hrv_ms"] == 45
        assert result["hrv_status"] == "BALANCED"
        # Raw keys must not leak
        assert "dailySleepDTO" not in result
        assert "wellnessSpO2SleepSummaryDTO" not in result

    def test_no_data_is_unavailable(self, client):
        client.get_sleep_data.return_value = None
        result = api.get_sleep(client, "2024-01-15")
        assert result == NO_DATA_DAY

    def test_empty_dto_is_unavailable(self, client):
        client.get_sleep_data.return_value = {"dailySleepDTO": {}}
        assert api.get_sleep(client, "2024-01-15") == NO_DATA_DAY


# ── get_stats ────────────────────────────────────────────────────────────────


class TestGetStats:
    def test_curates_essential_fields(self, client):
        client.get_user_summary.return_value = {
            "calendarDate": "2024-01-15",
            "totalSteps": 10000,
            "totalKilocalories": 2500,
            "restingHeartRate": 55,
            "averageStressLevel": 30,
            "bodyBatteryMostRecentValue": 75,
            "averageSpo2": 96,
            "privacyProtected": False,
        }
        result = api.get_stats(client, "2024-01-15")
        assert result["steps"] == 10000
        assert result["total_calories_kcal"] == 2500
        assert result["resting_hr_bpm"] == 55
        assert result["avg_stress"] == 30
        assert result["body_battery_current"] == 75
        assert result["avg_spo2_percent"] == 96
        # Raw Garmin keys must not leak
        assert "privacyProtected" not in result
        assert "calendarDate" not in result or result.get("date") is not None

    def test_no_data_is_unavailable(self, client):
        client.get_user_summary.return_value = None
        assert api.get_stats(client, "2024-01-15") == NO_DATA_DAY

    def test_only_a_date_is_unavailable(self, client):
        """A day Garmin knows but has no value for (future day, watch not worn)."""
        client.get_user_summary.return_value = {"calendarDate": "2024-01-15", "totalSteps": None}
        assert api.get_stats(client, "2024-01-15") == NO_DATA_DAY

    def test_partial_day_says_synced_until(self, client):
        """The watch has sent the day up to 08:20 only: the steps are not the day's total."""
        client.get_user_summary.return_value = {
            "calendarDate": "2024-01-15", "totalSteps": 21,
            "wellnessEndTimeLocal": "2024-01-15T08:20:00.0",
        }
        assert api.get_stats(client, "2024-01-15")["synced_until"] == "2024-01-15T08:20:00"

    def test_complete_day_has_no_synced_until(self, client):
        client.get_user_summary.return_value = {
            "calendarDate": "2024-01-15", "totalSteps": 10000,
            "wellnessEndTimeLocal": "2024-01-16T00:00:00.0",
        }
        assert "synced_until" not in api.get_stats(client, "2024-01-15")


# ── get_stress ───────────────────────────────────────────────────────────────


class TestGetStress:
    def test_with_distribution(self, client):
        client.get_stress_data.return_value = {
            "calendarDate": "2024-01-15",
            "maxStressLevel": 80,
            "avgStressLevel": 35,
            "stressValuesArray": [
                [1, 10], [2, 20], [3, 50], [4, 80], [5, 30],
            ],
        }
        result = api.get_stress(client, "2024-01-15")
        assert (result["avg_stress"], result["max_stress"]) == (35, 80)
        # samples 10, 20 rest; 50, 30 low; 80 high
        assert result["rest_stress_percent"] == 40.0
        assert result["low_stress_percent"] == 40.0
        assert result["medium_stress_percent"] == 0.0
        assert result["high_stress_percent"] == 20.0

    def test_no_data_is_unavailable(self, client):
        client.get_stress_data.return_value = None
        assert api.get_stress(client, "2024-01-15") == NO_DATA_DAY


# ── get_heart_rate ───────────────────────────────────────────────────────────


class TestGetHeartRate:
    def test_summary(self, client):
        client.get_heart_rates.return_value = {
            "calendarDate": "2024-01-15",
            "maxHeartRate": 180,
            "minHeartRate": 45,
            "restingHeartRate": 55,
            "lastSevenDaysAvgRestingHeartRate": 57,
            "heartRateValues": [[1, 60], [2, 70], [3, 80]],
        }
        result = api.get_heart_rate(client, "2024-01-15")
        assert result["resting_hr_bpm"] == 55
        assert result["resting_hr_7d_avg_bpm"] == 57
        assert (result["min_hr_bpm"], result["max_hr_bpm"]) == (45, 180)
        assert result["avg_hr_bpm"] == 70
        assert "heartRateValues" not in result


# ── get_respiration ──────────────────────────────────────────────────────────


class TestGetRespiration:
    def test_summary(self, client):
        client.get_respiration_data.return_value = {
            "calendarDate": "2024-01-15",
            "lowestRespirationValue": 12,
            "highestRespirationValue": 22,
            "avgWakingRespirationValue": 16,
            "avgSleepRespirationValue": 14,
        }
        result = api.get_respiration(client, "2024-01-15")
        assert (result["min_respiration_brpm"], result["max_respiration_brpm"]) == (12, 22)
        assert result["avg_waking_respiration_brpm"] == 16
        assert result["avg_sleep_respiration_brpm"] == 14


# ── get_body_battery ─────────────────────────────────────────────────────────


class TestGetBodyBattery:
    def test_with_events(self, client):
        client.get_body_battery.return_value = [
            {
                "date": "2024-01-15",
                "charged": 50,
                "drained": 30,
                "bodyBatteryValuesArray": [[1, 20], [2, 80], [3, None], [4, 35]],
                "bodyBatteryActivityEvent": [
                    {
                        "eventType": "SLEEP",
                        "eventStartTimeGmt": "2024-01-14T22:00:00.0",
                        "timezoneOffset": 3600000,
                        "durationInMilliseconds": 28800000,
                        "bodyBatteryImpact": 50,
                        "shortFeedback": "NONE",
                    }
                ],
                "bodyBatteryDynamicFeedbackEvent": {
                    "feedbackShortType": "SLEEP_PREPARATION_RECOVERING_AND_INACTIVE",
                    "bodyBatteryLevel": "HIGH",
                },
            }
        ]
        result = api.get_body_battery(client, "2024-01-15", "2024-01-15")
        assert result == {"count": 1, "days": [{
            "date": "2024-01-15",
            "body_battery_low": 20, "body_battery_high": 80,
            "body_battery_charged": 50, "body_battery_drained": 30,
            "body_battery_level": "HIGH",
            "body_battery_feedback": "SLEEP_PREPARATION_RECOVERING_AND_INACTIVE",
            # local start time: GMT + the event's offset
            "events": [{"type": "SLEEP", "start_time": "2024-01-14T23:00:00", "duration_s": 28800,
                        "body_battery_impact": 50, "feedback": "NONE"}],
        }]}


# ── get_coaching_snapshot ────────────────────────────────────────────────────


class TestGetCoachingSnapshot:
    @pytest.fixture
    def client(self):
        """One answer per section endpoint, called with the date."""
        client = Mock()
        client.get_user_summary.return_value = {
            "calendarDate": "2024-01-15", "totalSteps": 8000, "restingHeartRate": 55,
        }
        client.get_sleep_data.return_value = {
            "dailySleepDTO": {
                "sleepTimeSeconds": 25200,
                "sleepScores": {"overall": {"value": 80}},
                "deepSleepSeconds": 6000,
                "lightSleepSeconds": 12000,
                "remSleepSeconds": 5400,
                "awakeSleepSeconds": 1800,
            },
        }
        client.get_training_readiness.return_value = [
            {"calendarDate": "2024-01-15", "score": 65, "level": "MODERATE"}
        ]
        client.get_hrv_data.return_value = {
            "hrvSummary": {"lastNightAvg": 45, "weeklyAvg": 48, "status": "BALANCED",
                           "feedbackPhrase": "HRV_BALANCED_2"},
        }
        return client

    def test_composites_all_fields(self, client):
        result = api.get_coaching_snapshot(client, "2024-01-15")
        assert result["date"] == "2024-01-15"
        assert result["stats"] == {"steps": 8000, "resting_hr_bpm": 55}
        assert result["sleep"] == {"sleep_score": 80, "sleep_s": 25200, "deep_sleep_s": 6000,
                                   "light_sleep_s": 12000, "rem_sleep_s": 5400, "awake_s": 1800}
        assert result["training_readiness"] == {"score": 65, "level": "MODERATE"}
        # the HRV keeps the reason of its status
        assert result["hrv"] == {"last_night_avg_hrv_ms": 45, "weekly_avg_hrv_ms": 48,
                                 "hrv_status": "BALANCED", "hrv_feedback": "HRV_BALANCED_2"}
        # no body battery section: its numbers are in the stats
        assert "body_battery" not in result
        client.get_hrv_data.assert_called_once_with("2024-01-15")

    def test_snapshot_sections_are_short(self, client):
        """The overview keeps the essentials; the rest is in `health stats`."""
        client.get_user_summary.return_value = {
            "calendarDate": "2024-01-15", "totalSteps": 8000, "restingHeartRate": 55,
            "totalKilocalories": 2500, "sedentarySeconds": 40000, "minHeartRate": 45,
        }
        assert api.get_coaching_snapshot(client, "2024-01-15")["stats"] == {"steps": 8000, "resting_hr_bpm": 55}

    def test_section_without_data_says_no_data(self, client):
        client.get_sleep_data.return_value = None
        client.get_training_readiness.return_value = []
        client.get_hrv_data.return_value = {}
        result = api.get_coaching_snapshot(client, "2024-01-15")
        assert result["stats"]["steps"] == 8000
        for section in ("sleep", "training_readiness", "hrv"):
            assert result[section] == {"available": False, "reason": "no_data"}

    def test_readiness_not_computed_by_the_device_says_so(self, client):
        """Forerunner 165: no readiness, `hasTrainingReadinessCapableDevice: false`."""
        client.get_training_readiness.return_value = []
        client.get_hrv_data.return_value = {}
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {"hasTrainingReadinessCapableDevice": False},
        }
        result = api.get_coaching_snapshot(client, "2024-01-15")
        assert result["training_readiness"] == {"available": False, "reason": "not_supported_by_device"}
        assert result["hrv"] == {"available": False, "reason": "no_data"}  # no device reason for HRV yet
        client.get_usage_indicators.assert_called_once()

    def test_sections_with_data_read_no_capabilities(self, client):
        api.get_coaching_snapshot(client, "2024-01-15")
        client.get_usage_indicators.assert_not_called()

    def test_failed_section_says_why(self, client):
        """A 429 on one endpoint is not "no data": the reason carries the error."""
        client.get_hrv_data.side_effect = GarminConnectTooManyRequestsError("Rate limit exceeded")
        result = api.get_coaching_snapshot(client, "2024-01-15")
        assert result["stats"]["steps"] == 8000
        assert result["hrv"]["available"] is False
        assert result["hrv"]["reason"].startswith("error: Garmin rate limit (HTTP 429)")

    def test_curation_error_stays_in_its_section(self, client):
        client.get_sleep_data.return_value = {"dailySleepDTO": {"sleepStartTimestampLocal": "not a number"}}
        result = api.get_coaching_snapshot(client, "2024-01-15")
        assert result["sleep"]["reason"].startswith("error: TypeError")
        assert result["stats"]["steps"] == 8000

    def test_auth_error_fails_the_snapshot(self, client):
        client.get_user_summary.side_effect = GarminConnectAuthenticationError("401")
        with pytest.raises(AuthError):
            api.get_coaching_snapshot(client, "2024-01-15")
        client.get_hrv_data.assert_not_called()

    def test_every_section_failing_fails_the_snapshot(self, client):
        error = GarminConnectTooManyRequestsError("Rate limit exceeded")
        for method in ("get_user_summary", "get_sleep_data", "get_training_readiness", "get_hrv_data"):
            getattr(client, method).side_effect = error
        with pytest.raises(RateLimited):
            api.get_coaching_snapshot(client, "2024-01-15")

    def test_some_failures_and_no_data_is_an_answer(self, client):
        client.get_user_summary.side_effect = GarminConnectConnectionError("timeout")
        client.get_sleep_data.return_value = None
        result = api.get_coaching_snapshot(client, "2024-01-15")
        assert result["stats"]["reason"] == "error: Garmin did not answer: timeout"
        assert result["sleep"]["reason"] == "no_data"
        assert result["hrv"]["hrv_status"] == "BALANCED"


# ── get_spo2 ─────────────────────────────────────────────────────────────────


class TestGetSpo2:
    def test_curates_fields(self, client):
        client.get_spo2_data.return_value = {
            "calendarDate": "2024-01-15",
            "averageSpO2": 96,
            "lowestSpO2": 93,
            "latestSpO2": 97,
            "lastSevenDaysAvgSpO2": 96,
        }
        result = api.get_spo2(client, "2024-01-15")
        assert result["avg_spo2_percent"] == 96
        assert result["lowest_spo2_percent"] == 93


# ── get_training_readiness ───────────────────────────────────────────────────


class TestGetTrainingReadiness:
    def test_single_entry(self, client):
        client.get_training_readiness.return_value = [
            {
                "calendarDate": "2024-01-15",
                "score": 72,
                "level": "MODERATE",
                "feedbackShort": "Moderate readiness",
                "sleepScore": 80,
                "recoveryTime": 120,
                "acuteLoad": 450,
            }
        ]
        result = api.get_training_readiness(client, "2024-01-15")
        assert result["score"] == 72
        assert result["level"] == "MODERATE"
        assert result["feedback"] == "Moderate readiness"
        assert result["recovery_time_s"] == 7200
        assert "latest_score" not in result

    def test_morning_reading_and_the_last_update(self, client):
        """Garmin updates the readiness during the day: the morning's is the reference."""
        client.get_training_readiness.return_value = [
            {"calendarDate": "2024-01-15", "score": 60, "timestamp": "2024-01-15T17:00:00.0",
             "timestampLocal": "2024-01-15T18:00:00.0", "inputContext": "UPDATE_REALTIME_VARIABLES"},
            {"calendarDate": "2024-01-15", "score": 80, "timestamp": "2024-01-15T05:30:00.0",
             "timestampLocal": "2024-01-15T06:30:00.0", "inputContext": "AFTER_WAKEUP_RESET",
             "sleepScoreFactorPercent": 88, "hrvFactorFeedback": "GOOD"},
        ]
        result = api.get_training_readiness(client, "2024-01-15")
        assert result["score"] == 80
        assert result["measured_at"] == "2024-01-15T06:30:00"
        assert (result["sleep_factor_percent"], result["hrv_factor_feedback"]) == (88, "GOOD")
        assert (result["latest_score"], result["latest_at"]) == (60, "2024-01-15T18:00:00")

    def test_no_data_is_unavailable(self, client):
        client.get_training_readiness.return_value = []
        assert api.get_training_readiness(client, "2024-01-15") == NO_DATA_DAY

    def test_not_computed_by_the_device(self, client):
        client.get_training_readiness.return_value = []
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {"hasTrainingReadinessCapableDevice": False},
        }
        assert api.get_training_readiness(client, "2024-01-15") == {
            "date": "2024-01-15", "available": False, "reason": "not_supported_by_device",
        }


# ── Days without data ────────────────────────────────────────────────────────


@pytest.mark.parametrize("function, method", [
    (api.get_heart_rate, "get_heart_rates"),
    (api.get_respiration, "get_respiration_data"),
    (api.get_spo2, "get_spo2_data"),
])
def test_day_without_data_is_unavailable(client, function, method):
    """No data for a day is an answer that says so (exit 0), not an error."""
    getattr(client, method).return_value = None
    assert function(client, "2024-01-15") == NO_DATA_DAY


def test_body_battery_without_data_is_an_empty_list(client):
    client.get_body_battery.return_value = []
    assert api.get_body_battery(client, "2024-01-15", "2024-01-16") == {"count": 0, "days": []}
