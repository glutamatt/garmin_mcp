"""Unit tests for garmin_mcp.api.training — curation logic with mock client."""

import pytest
from unittest.mock import Mock
from garmin_mcp.api import training as api


@pytest.fixture
def client():
    return Mock()


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

    def test_no_data(self, client):
        client.get_max_metrics.return_value = None
        result = api.get_max_metrics(client, "2024-01-15")
        assert "error" in result


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

    def test_no_data(self, client):
        client.get_hrv_data.return_value = None
        result = api.get_hrv_data(client, "2024-01-15")
        assert "error" in result


class TestGetTrainingStatus:
    def test_curates_complex_structure(self, client):
        client.get_training_status.return_value = {
            "mostRecentTrainingStatus": {
                "latestTrainingStatusData": {
                    "device123": {
                        "calendarDate": "2024-01-15",
                        "trainingStatus": "PRODUCTIVE",
                        "trainingStatusFeedbackPhrase": "Your training is productive",
                        "sport": "RUNNING",
                        "fitnessTrend": "UP",
                        "acuteTrainingLoadDTO": {
                            "dailyTrainingLoadAcute": 500,
                            "dailyTrainingLoadChronic": 400,
                            "dailyAcuteChronicWorkloadRatio": 1.25,
                            "acwrStatus": "OPTIMAL",
                        },
                    }
                }
            },
            "mostRecentVO2Max": {"generic": {"vo2MaxValue": 52.5, "vo2MaxPreciseValue": 52.8}},
            "mostRecentTrainingLoadBalance": {
                "metricsTrainingLoadBalanceDTOMap": {
                    "device123": {
                        "monthlyLoadAerobicLow": 200,
                        "monthlyLoadAerobicHigh": 150,
                        "monthlyLoadAnaerobic": 50,
                    }
                }
            },
        }
        result = api.get_training_status(client, "2024-01-15")
        assert result["training_status"] == "PRODUCTIVE"
        assert result["acute_load"] == 500
        assert result["load_ratio"] == 1.25
        assert result["vo2_max"] == 52.5
        assert result["monthly_load_aerobic_low"] == 200

    def test_no_data(self, client):
        client.get_training_status.return_value = None
        result = api.get_training_status(client, "2024-01-15")
        assert "error" in result


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

    def test_no_data(self, client):
        client.get_progress_summary_between_dates.return_value = None
        result = api.get_progress_summary(client, "2024-01-01", "2024-01-15", "distance")
        assert "error" in result


class TestGetRacePredictions:
    def test_returns_raw(self, client):
        client.get_race_predictions.return_value = {"5K": "22:00", "10K": "46:00"}
        result = api.get_race_predictions(client)
        assert "5K" in result

    def test_no_data(self, client):
        client.get_race_predictions.return_value = None
        result = api.get_race_predictions(client)
        assert "error" in result


class TestGetGoals:
    def test_returns_data(self, client):
        client.get_goals.return_value = [{"goalType": "steps", "target": 10000}]
        result = api.get_goals(client, "active")
        assert isinstance(result, list)

    def test_no_data(self, client):
        client.get_goals.return_value = None
        result = api.get_goals(client)
        assert "error" in result


class TestGetPersonalRecord:
    def test_returns_data(self, client):
        client.get_personal_record.return_value = [{"recordType": "FASTEST_5K"}]
        result = api.get_personal_record(client)
        assert isinstance(result, list)
