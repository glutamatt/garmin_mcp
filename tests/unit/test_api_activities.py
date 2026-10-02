"""Unit tests for garmin_mcp.api.activities — curation logic with mock client."""

import io
import zipfile

import pytest
from unittest.mock import Mock, patch
from garmin_mcp.api import activities as api
from garmin_mcp.api.contract import InvalidInput, NotFound, Unavailable


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

    def test_no_data_date_range_is_an_empty_list(self, client):
        client.get_activities_by_date.return_value = []
        result = api.get_activities(client, "2024-01-01", "2024-01-15")
        assert result == {
            "count": 0,
            "date_range": {"start": "2024-01-01", "end": "2024-01-15"},
            "activities": [],
        }
        client.query_garmin_graphql.assert_not_called()

    def test_no_data_pagination_is_an_empty_list(self, client):
        client.get_activities.return_value = []
        result = api.get_activities(client)
        assert result["count"] == 0
        assert result["activities"] == []
        assert result["has_more"] is False

    def test_limit_capped(self, client):
        client.get_activities.return_value = []
        api.get_activities(client, limit=999)
        client.get_activities.assert_called_with(0, 100)


class TestGraphQLEnrichment:
    def test_enriches_training_load_when_no_fields_filter(self, client):
        """GraphQL enrichment adds training_load when fields=None (no filter)."""
        client.get_activities_by_date.return_value = [SAMPLE_RAW_ACTIVITY]
        client.display_name = "test-user"
        client.query_garmin_graphql.return_value = {
            "data": {
                "activitiesScalar": {
                    "activityList": [
                        {"activityId": 12345, "activityTrainingLoad": 142.5}
                    ]
                }
            }
        }
        result = api.get_activities(client, "2024-01-01", "2024-01-15")
        assert result["activities"][0]["training_load"] == 142.5
        client.query_garmin_graphql.assert_called_once()

    def test_enriches_when_training_load_in_fields(self, client):
        """GraphQL call made when training_load is in requested fields."""
        client.get_activities_by_date.return_value = [SAMPLE_RAW_ACTIVITY]
        client.display_name = "test-user"
        client.query_garmin_graphql.return_value = {
            "data": {
                "activitiesScalar": {
                    "activityList": [
                        {"activityId": 12345, "activityTrainingLoad": 100.0}
                    ]
                }
            }
        }
        result = api.get_activities(
            client, "2024-01-01", "2024-01-15",
            fields=["id", "training_load"],
        )
        assert result["activities"][0]["training_load"] == 100.0

    def test_skips_graphql_when_field_not_requested(self, client):
        """No GraphQL call when training_load is not in requested fields."""
        client.get_activities_by_date.return_value = [SAMPLE_RAW_ACTIVITY]
        result = api.get_activities(
            client, "2024-01-01", "2024-01-15",
            fields=["id", "name", "distance_meters"],
        )
        assert "training_load" not in result["activities"][0]
        client.query_garmin_graphql.assert_not_called()

    def test_graphql_failure_doesnt_crash(self, client):
        """GraphQL errors are silently ignored."""
        client.get_activities_by_date.return_value = [SAMPLE_RAW_ACTIVITY]
        client.display_name = "test-user"
        client.query_garmin_graphql.side_effect = Exception("GraphQL down")
        result = api.get_activities(client, "2024-01-01", "2024-01-15")
        assert result["count"] == 1
        assert "training_load" not in result["activities"][0]

    def test_pagination_mode_enriches(self, client):
        """Pagination mode also enriches via GraphQL."""
        client.get_activities.return_value = [SAMPLE_RAW_ACTIVITY]
        client.display_name = "test-user"
        client.query_garmin_graphql.return_value = {
            "data": {
                "activitiesScalar": {
                    "activityList": [
                        {"activityId": 12345, "activityTrainingLoad": 88.0}
                    ]
                }
            }
        }
        result = api.get_activities(client, start=0, limit=5)
        assert result["activities"][0]["training_load"] == 88.0


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

    def test_no_data_is_not_found(self, client):
        client.get_activity.return_value = None
        with pytest.raises(NotFound, match="99999"):
            api.get_activity(client, 99999)


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

    def test_no_splits_is_an_empty_list(self, client):
        client.get_activity_splits.return_value = None
        assert api.get_activity_splits(client, 12345) == {
            "activity_id": 12345, "lap_count": 0, "laps": [],
        }


class TestGetActivityHrInTimezones:
    def test_no_zones_is_an_empty_list(self, client):
        client.get_activity_hr_in_timezones.return_value = None
        assert api.get_activity_hr_in_timezones(client, 12345) == []


class TestDownloadActivity:
    def test_unsupported_format_is_invalid_input(self, client, tmp_path):
        with pytest.raises(InvalidInput, match="Unsupported format"):
            api.download_activity(client, 1, "pdf", str(tmp_path))
        client.download_activity.assert_not_called()

    @staticmethod
    def _zip(names: list[str]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            for name in names:
                zf.writestr(name, b"fit bytes")
        return buffer.getvalue()

    def test_zip_without_fit_is_unavailable(self, client, tmp_path):
        client.download_activity.return_value = self._zip(["activity.txt"])
        with pytest.raises(Unavailable, match="no .fit file"):
            api.download_activity(client, 1, "fit", str(tmp_path))

    def test_fit_without_samples_is_an_empty_csv(self, client, tmp_path):
        """A manual activity has no record: an empty file and `rows: 0`, not an error."""
        client.download_activity.return_value = self._zip(["1_ACTIVITY.fit"])
        fit = Mock()
        fit.get_messages.return_value = []
        with patch("fitparse.FitFile", return_value=fit):
            result = api.download_activity(client, 1, "fit", str(tmp_path))
        assert result["rows"] == 0
        assert result["columns"] == []
        assert open(result["path"]).read() == ""


class TestGetActivityTypes:
    def test_no_types_is_an_empty_list(self, client):
        client.get_activity_types.return_value = None
        assert api.get_activity_types(client) == {"count": 0, "activity_types": []}

    def test_curates_list(self, client):
        client.get_activity_types.return_value = [
            {"typeId": 1, "typeKey": "running", "displayName": "Running", "parentTypeId": 17},
            {"typeId": 2, "typeKey": "cycling", "displayName": "Cycling", "parentTypeId": 17},
        ]
        result = api.get_activity_types(client)
        assert result["count"] == 2
        assert result["activity_types"][0]["type_key"] == "running"
