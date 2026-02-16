"""Unit tests for garmin_mcp.api.activities — curation logic with mock client."""

import pytest
from unittest.mock import Mock
from garmin_mcp.api import activities as api


@pytest.fixture
def client():
    return Mock()


SAMPLE_RAW_ACTIVITY = {
    "activityId": 12345,
    "activityName": "Morning Run",
    "activityType": {"typeKey": "running", "typeId": 1},
    "startTimeLocal": "2024-01-15 07:00:00",
    "distance": 10000.0,
    "duration": 3000.0,
    "movingDuration": 2900.0,
    "averageHR": 150,
    "maxHR": 175,
    "calories": 500,
    "steps": 8000,
}


class TestGetActivities:
    def test_date_range_mode(self, client):
        client.get_activities_by_date.return_value = [SAMPLE_RAW_ACTIVITY]
        result = api.get_activities(client, "2024-01-01", "2024-01-15")
        assert result["count"] == 1
        assert result["date_range"]["start"] == "2024-01-01"
        a = result["activities"][0]
        assert a["id"] == 12345
        assert a["type"] == "running"
        assert a["distance_meters"] == 10000.0
        # Raw keys must not leak
        assert "activityId" not in a
        assert "activityType" not in a

    def test_pagination_mode(self, client):
        client.get_activities.return_value = [SAMPLE_RAW_ACTIVITY] * 5
        result = api.get_activities(client, start=0, limit=5)
        assert result["count"] == 5
        assert result["has_more"] is True
        assert result["next_start"] == 5

    def test_no_data_date_range(self, client):
        client.get_activities_by_date.return_value = []
        result = api.get_activities(client, "2024-01-01", "2024-01-15")
        assert "error" in result

    def test_no_data_pagination(self, client):
        client.get_activities.return_value = []
        result = api.get_activities(client)
        assert "error" in result

    def test_limit_capped(self, client):
        client.get_activities.return_value = []
        api.get_activities(client, limit=999)
        client.get_activities.assert_called_with(0, 100)


class TestGetActivity:
    def test_curates_detail(self, client):
        client.get_activity.return_value = {
            "activityId": 12345,
            "activityName": "Morning Run",
            "activityTypeDTO": {"typeKey": "running"},
            "summaryDTO": {
                "startTimeLocal": "2024-01-15 07:00:00",
                "duration": 3000.0,
                "distance": 10000.0,
                "averageSpeed": 3.33,
                "averageHR": 150,
                "maxHR": 175,
                "calories": 500,
                "trainingEffect": 3.5,
                "anaerobicTrainingEffect": 1.2,
                "activityTrainingLoad": 85,
            },
            "metadataDTO": {"lapCount": 5, "hasSplits": True},
        }
        client.get_activity_weather.return_value = None
        result = api.get_activity(client, 12345)
        assert result["id"] == 12345
        assert result["type"] == "running"
        assert result["training_effect"] == 3.5
        assert result["training_load"] == 85
        assert result["lap_count"] == 5

    def test_no_data(self, client):
        client.get_activity.return_value = None
        result = api.get_activity(client, 99999)
        assert "error" in result


class TestGetActivitySplits:
    def test_curates_laps(self, client):
        client.get_activity_splits.return_value = {
            "activityId": 12345,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "averageSpeed": 3.33,
                    "averageHR": 145,
                    "maxHR": 155,
                },
                {
                    "lapIndex": 2,
                    "distance": 1000.0,
                    "duration": 280.0,
                    "averageSpeed": 3.57,
                    "averageHR": 160,
                    "maxHR": 170,
                },
            ],
        }
        result = api.get_activity_splits(client, 12345)
        assert result["lap_count"] == 2
        assert result["laps"][0]["lap_number"] == 1
        assert result["laps"][1]["avg_hr_bpm"] == 160


class TestGetActivityTypes:
    def test_curates_list(self, client):
        client.get_activity_types.return_value = [
            {"typeId": 1, "typeKey": "running", "displayName": "Running", "parentTypeId": 17},
            {"typeId": 2, "typeKey": "cycling", "displayName": "Cycling", "parentTypeId": 17},
        ]
        result = api.get_activity_types(client)
        assert result["count"] == 2
        assert result["activity_types"][0]["type_key"] == "running"
