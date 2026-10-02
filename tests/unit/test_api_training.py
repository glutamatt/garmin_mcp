"""Unit tests for garmin_mcp.api.training — curation logic with mock client."""

import pytest
from unittest.mock import Mock
from garmin_mcp.api import training as api


@pytest.fixture
def client():
    return Mock()


NO_DATA_DAY = {"date": "2024-01-15", "available": False, "reason": "no_data"}


class TestGetMaxMetrics:
    def test_single_metric(self, client):
        client.get_max_metrics.return_value = {
            "metricType": "RUNNING",
            "vo2MaxValue": 52.5,
            "fitnessAge": 25,
            "chronologicalAge": 35,
            "lactateThresholdHeartRate": 170,
            "lactateThresholdSpeed": 3.5,
        }
        result = api.get_max_metrics(client, "2024-01-15")
        assert result["vo2_max"] == 52.5
        assert result["fitness_age_years"] == 25
        assert result["lactate_threshold_hr_bpm"] == 170

    def test_list_of_metrics(self, client):
        client.get_max_metrics.return_value = [
            {"metricType": "RUNNING", "vo2MaxValue": 52.5},
            {"metricType": "CYCLING", "vo2MaxValue": 48.0},
        ]
        result = api.get_max_metrics(client, "2024-01-15")
        assert "metrics" in result
        assert len(result["metrics"]) == 2

    def test_no_data_is_unavailable(self, client):
        client.get_max_metrics.return_value = None
        assert api.get_max_metrics(client, "2024-01-15") == NO_DATA_DAY


class TestGetHrvData:
    def test_curates_summary(self, client):
        client.get_hrv_data.return_value = {
            "hrvSummary": {
                "calendarDate": "2024-01-15",
                "lastNightAvg": 45,
                "lastNight5MinHigh": 65,
                "weeklyAvg": 48,
                "baseline": {"balancedLow": 35, "balancedUpper": 55},
                "status": "BALANCED",
                "feedbackPhrase": "Your HRV is balanced",
            }
        }
        result = api.get_hrv_data(client, "2024-01-15")
        assert result["last_night_avg_hrv_ms"] == 45
        assert result["weekly_avg_hrv_ms"] == 48
        assert result["status"] == "BALANCED"
        assert result["baseline_balanced_low_ms"] == 35

    def test_no_data_is_unavailable(self, client):
        client.get_hrv_data.return_value = None
        assert api.get_hrv_data(client, "2024-01-15") == NO_DATA_DAY


def _status_entry(device_id, date, primary, **extra):
    """One device entry of `latestTrainingStatusData`, Garmin's shape (python-garminconnect docs)."""
    return {
        "calendarDate": date, "sinceDate": "2024-06-28", "weeklyTrainingLoad": None,
        "trainingStatus": 7, "timestamp": 1720445627000, "deviceId": device_id,
        "loadTunnelMin": None, "loadTunnelMax": None, "sport": "RUNNING", "fitnessTrend": 2,
        "trainingStatusFeedbackPhrase": "PRODUCTIVE_3", "trainingPaused": False,
        "acuteTrainingLoadDTO": {
            "acwrPercent": 33, "acwrStatus": "OPTIMAL", "acwrStatusFeedback": "FEEDBACK_2",
            "dailyTrainingLoadAcute": 886, "maxTrainingLoadChronic": 1506.0,
            "minTrainingLoadChronic": 803.2, "dailyTrainingLoadChronic": 1004,
            "dailyAcuteChronicWorkloadRatio": 0.8,
        },
        "primaryTrainingDevice": primary,
        **extra,
    }


def _balance_entry(device_id, primary):
    return {
        "calendarDate": "2024-07-08", "deviceId": device_id,
        "monthlyLoadAerobicLow": 1926.3918, "monthlyLoadAerobicHigh": 1651.8569,
        "monthlyLoadAnaerobic": 260.00317,
        "monthlyLoadAerobicLowTargetMin": 1404, "monthlyLoadAerobicLowTargetMax": 2282,
        "monthlyLoadAerobicHighTargetMin": 1229, "monthlyLoadAerobicHighTargetMax": 2107,
        "monthlyLoadAnaerobicTargetMin": 175, "monthlyLoadAnaerobicTargetMax": 702,
        "trainingBalanceFeedbackPhrase": "ON_TARGET", "primaryTrainingDevice": primary,
    }


def _training_status(status_entries, balance_entries=(), devices=()):
    return {
        "userId": 1,
        "mostRecentVO2Max": {"generic": {"vo2MaxValue": 52.0, "vo2MaxPreciseValue": 52.4}},
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {str(e["deviceId"]): e for e in status_entries},
            "recordedDevices": [{"deviceId": i, "deviceName": name} for i, name in devices],
        },
        "mostRecentTrainingLoadBalance": {
            "metricsTrainingLoadBalanceDTOMap": {str(e["deviceId"]): e for e in balance_entries},
            "recordedDevices": [{"deviceId": i, "deviceName": name} for i, name in devices],
        },
        "heatAltitudeAcclimationDTO": None,
    }


def _flags(**flags):
    return {"deviceBasedIndicators": flags}


class TestGetTrainingStatus:
    def test_curates_the_main_device(self, client):
        client.get_training_status.return_value = _training_status(
            [_status_entry(11, "2024-07-08", True)], [_balance_entry(11, True)], [(11, "Forerunner 965")],
        )
        assert api.get_training_status(client, "2024-07-08") == {
            "date": "2024-07-08",
            "device": "Forerunner 965",
            "device_id": 11,
            "training_status": "PRODUCTIVE",
            "training_status_feedback": "PRODUCTIVE_3",
            "training_paused": False,
            "sport": "RUNNING",
            "fitness_trend": 2,
            "acute_load": 886,
            "chronic_load": 1004,
            "load_ratio": 0.8,
            "acwr_status": "OPTIMAL",
            "acwr_status_feedback": "FEEDBACK_2",
            "acwr_percent": 33,
            "optimal_chronic_load_min": 803,
            "optimal_chronic_load_max": 1506,
            "vo2_max": 52.0,
            "vo2_max_precise": 52.4,
            "monthly_load_aerobic_low": 1926,
            "monthly_load_aerobic_low_target_min": 1404,
            "monthly_load_aerobic_low_target_max": 2282,
            "monthly_load_aerobic_high": 1652,
            "monthly_load_aerobic_high_target_min": 1229,
            "monthly_load_aerobic_high_target_max": 2107,
            "monthly_load_anaerobic": 260,
            "monthly_load_anaerobic_target_min": 175,
            "monthly_load_anaerobic_target_max": 702,
            "training_balance_feedback": "ON_TARGET",
        }
        client.get_usage_indicators.assert_not_called()  # data: no capability call

    def test_the_primary_device_wins_over_the_first_and_the_latest(self, client):
        client.get_training_status.return_value = _training_status(
            [
                _status_entry(21, "2024-07-08", False, trainingStatusFeedbackPhrase="RECOVERY_1"),
                _status_entry(22, "2024-07-01", True, trainingStatusFeedbackPhrase="MAINTAINING_3"),
            ],
            [_balance_entry(21, False), {**_balance_entry(22, True), "monthlyLoadAnaerobic": 99.6}],
            [(21, "Edge 540"), (22, "Fenix 8")],
        )
        result = api.get_training_status(client, "2024-07-08")
        assert result["device"] == "Fenix 8"
        assert result["training_status"] == "MAINTAINING"
        assert result["monthly_load_anaerobic"] == 100

    def test_without_a_primary_device_the_latest_entry(self, client):
        client.get_training_status.return_value = _training_status([
            _status_entry(31, "2024-07-01", False, trainingStatusFeedbackPhrase="RECOVERY_1"),
            _status_entry(32, "2024-07-08", False, trainingStatusFeedbackPhrase="PEAKING_1"),
        ])
        assert api.get_training_status(client, "2024-07-08")["training_status"] == "PEAKING"

    def test_weekly_load_of_a_device_without_acwr(self, client):
        entry = _status_entry(41, "2024-07-08", True, weeklyTrainingLoad=612.4,
                              loadTunnelMin=402.0, loadTunnelMax=780.9, acuteTrainingLoadDTO=None)
        client.get_training_status.return_value = _training_status([entry])
        result = api.get_training_status(client, "2024-07-08")
        assert (result["weekly_training_load"], result["optimal_weekly_load_min"],
                result["optimal_weekly_load_max"]) == (612, 402, 781)
        assert "acute_load" not in result

    def test_a_phrase_without_a_number_keeps_garmin_status(self, client):
        entry = _status_entry(51, "2024-07-08", True, trainingStatus=0, trainingStatusFeedbackPhrase="NO_STATUS")
        client.get_training_status.return_value = _training_status([entry])
        assert api.get_training_status(client, "2024-07-08")["training_status"] == 0

    def test_no_data_is_unavailable(self, client):
        client.get_training_status.return_value = None
        assert api.get_training_status(client, "2024-01-15") == NO_DATA_DAY

    ALL_NULL = {
        "userId": 1, "mostRecentVO2Max": None, "mostRecentTrainingLoadBalance": None,
        "mostRecentTrainingStatus": None, "heatAltitudeAcclimationDTO": None,
    }

    def test_all_null_on_a_capable_device_is_no_data(self, client):
        """A watch that computes it, a day without: Garmin answers an object of nulls."""
        client.get_training_status.return_value = self.ALL_NULL
        client.get_usage_indicators.return_value = _flags(hasTrainingStatusCapableDevice=True)
        assert api.get_training_status(client, "2024-01-15") == NO_DATA_DAY

    def test_all_null_on_a_device_without_training_status(self, client):
        """Forerunner 165: `hasTrainingStatusCapableDevice: false`."""
        client.get_training_status.return_value = self.ALL_NULL
        client.get_usage_indicators.return_value = _flags(hasTrainingStatusCapableDevice=False)
        assert api.get_training_status(client, "2024-01-15") == {
            "date": "2024-01-15", "available": False, "reason": "not_supported_by_device",
        }


class TestGetProgressSummary:
    def test_distance_metric(self, client):
        client.get_progress_summary_between_dates.return_value = [
            {
                "date": "2024-01-15",
                "countOfActivities": 10,
                "stats": {
                    "running": {
                        "distance": {
                            "count": 10,
                            "min": 300000,
                            "max": 1000000,
                            "avg": 500000,
                            "sum": 5000000,
                        }
                    }
                },
            }
        ]
        result = api.get_progress_summary(client, "2024-01-01", "2024-01-15", "distance")
        assert result["entries"][0]["activity_type"] == "running"
        assert result["entries"][0]["activity_count"] == 10
        assert result["entries"][0]["total_distance_meters"] == 50000.0
        assert result["total_activities"] == 10

    def test_no_data_is_an_empty_list(self, client):
        client.get_progress_summary_between_dates.return_value = None
        result = api.get_progress_summary(client, "2024-01-01", "2024-01-15", "distance")
        assert result["total_activities"] == 0
        assert result["entries"] == []


class TestGetRacePredictions:
    def test_returns_raw(self, client):
        client.get_race_predictions.return_value = {"5K": "22:00", "10K": "46:00"}
        result = api.get_race_predictions(client)
        assert "5K" in result

    def test_no_data_is_unavailable(self, client):
        client.get_race_predictions.return_value = None
        assert api.get_race_predictions(client) == {"available": False, "reason": "no_data"}


class TestGetGoals:
    def test_returns_data(self, client):
        client.get_goals.return_value = [{"goalType": "steps", "target": 10000}]
        result = api.get_goals(client, "active")
        assert isinstance(result, list)

    def test_no_data_is_an_empty_list(self, client):
        client.get_goals.return_value = None
        assert api.get_goals(client) == []


class TestGetPersonalRecord:
    def test_returns_data(self, client):
        client.get_personal_record.return_value = [{"recordType": "FASTEST_5K"}]
        result = api.get_personal_record(client)
        assert isinstance(result, list)
