"""Unit tests for garmin_mcp.api.health — curation logic with mock client."""

import pytest
from unittest.mock import Mock
from garmin_mcp.api import health as api


@pytest.fixture
def client():
    return Mock()


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
                "restingHeartRate": 55,
                "avgSleepStress": 15,
                "sleepScores": {"overall": {"value": 85, "qualifierKey": "GOOD"}},
            },
            "wellnessSpO2SleepSummaryDTO": {"averageSpo2": 96, "lowestSpo2": 93},
            "avgOvernightHrv": 45,
        }
        result = api.get_sleep(client, "2024-01-15")
        assert result["sleep_score"] == 85
        assert result["total_sleep_hours"] == 8.0
        assert result["deep_sleep_hours"] == 2.0
        assert result["avg_spo2"] == 96
        assert result["avg_overnight_hrv"] == 45
        # Raw keys must not leak
        assert "dailySleepDTO" not in result
        assert "wellnessSpO2SleepSummaryDTO" not in result

    def test_no_data(self, client):
        client.get_sleep_data.return_value = None
        result = api.get_sleep(client, "2024-01-15")
        assert "error" in result

    def test_empty_dto(self, client):
        client.get_sleep_data.return_value = {"dailySleepDTO": {}}
        result = api.get_sleep(client, "2024-01-15")
        # Should return a dict (possibly empty), not crash
        assert isinstance(result, dict)


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
        assert result["total_steps"] == 10000
        assert result["resting_heart_rate_bpm"] == 55
        assert result["body_battery_current"] == 75
        # Raw Garmin keys must not leak
        assert "privacyProtected" not in result
        assert "calendarDate" not in result or result.get("date") is not None

    def test_no_data(self, client):
        client.get_user_summary.return_value = None
        result = api.get_stats(client, "2024-01-15")
        assert "error" in result


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
        assert result["max_stress_level"] == 80
        assert "rest_percent" in result
        assert "high_stress_percent" in result

    def test_no_data(self, client):
        client.get_stress_data.return_value = None
        result = api.get_stress(client, "2024-01-15")
        assert "error" in result


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
        assert result["resting_heart_rate_bpm"] == 55
        assert result["avg_heart_rate_bpm"] == 70.0
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
        assert result["lowest_breaths_per_min"] == 12
        assert result["avg_waking_breaths_per_min"] == 16


# ── get_body_battery ─────────────────────────────────────────────────────────


class TestGetBodyBattery:
    def test_with_events(self, client):
        client.get_body_battery.return_value = [
            {
                "date": "2024-01-15",
                "charged": 50,
                "drained": 30,
                "bodyBatteryActivityEvent": [
                    {
                        "eventType": "SLEEP",
                        "eventStartTimeGmt": "2024-01-15T00:00:00",
                        "durationInMilliseconds": 28800000,
                        "bodyBatteryImpact": 50,
                        "shortFeedback": "Good sleep",
                    }
                ],
                "bodyBatteryDynamicFeedbackEvent": {
                    "feedbackShortType": "GOOD",
                    "bodyBatteryLevel": 75,
                },
            }
        ]
        result = api.get_body_battery(client, "2024-01-15", "2024-01-15")
        assert len(result["days"]) == 1
        day = result["days"][0]
        assert day["charged"] == 50
        assert len(day["events"]) == 1
        assert day["events"][0]["type"] == "SLEEP"
        assert day["current_feedback"] == "GOOD"


# ── get_coaching_snapshot ────────────────────────────────────────────────────


class TestGetCoachingSnapshot:
    def test_composites_all_fields(self, client):
        client.get_coaching_snapshot.return_value = {
            "date": "2024-01-15",
            "stats": {"calendarDate": "2024-01-15", "totalSteps": 8000, "restingHeartRate": 55},
            "sleep": {
                "dailySleepDTO": {
                    "sleepTimeSeconds": 25200,
                    "sleepScores": {"overall": {"value": 80}},
                    "deepSleepSeconds": 6000,
                    "lightSleepSeconds": 12000,
                    "remSleepSeconds": 5400,
                    "awakeSleepSeconds": 1800,
                },
            },
            "training_readiness": [
                {"calendarDate": "2024-01-15", "score": 65, "level": "MODERATE"}
            ],
            "body_battery": [{"date": "2024-01-15", "charged": 40, "drained": 25}],
            "hrv": {"hrvSummary": {"lastNightAvg": 45, "weeklyAvg": 48, "status": "BALANCED"}},
        }
        result = api.get_coaching_snapshot(client, "2024-01-15")
        assert result["date"] == "2024-01-15"
        assert result["stats"]["total_steps"] == 8000
        assert result["sleep"]["sleep_score"] == 80
        assert result["training_readiness"]["score"] == 65
        assert result["body_battery"]["charged"] == 40
        assert result["hrv"]["status"] == "BALANCED"

    def test_handles_partial_data(self, client):
        client.get_coaching_snapshot.return_value = {
            "date": "2024-01-15",
            "stats": {"calendarDate": "2024-01-15", "totalSteps": 5000},
            "sleep": None,
            "training_readiness": None,
            "body_battery": None,
            "hrv": None,
        }
        result = api.get_coaching_snapshot(client, "2024-01-15")
        assert result["date"] == "2024-01-15"
        assert result["stats"]["total_steps"] == 5000
        # None fields should be stripped by clean_nones
        assert "sleep" not in result
        assert "hrv" not in result


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
        assert result["recovery_time_hours"] == 2.0
