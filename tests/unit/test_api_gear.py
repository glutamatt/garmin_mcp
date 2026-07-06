"""Unit tests for garmin_mcp.api.gear — merges filterGear metadata with usage stats.

Field names below are the REAL Garmin filterGear / gear-stats shapes (captured
live), not the legacy MOCK_GEAR fixture. The bug this guards: filterGear exposes
neither accumulated distance nor a usable name, so a naive mapping returned only
`uuid`.
"""

import pytest
from unittest.mock import Mock

from garmin_mcp.api import gear as api


# Real filterGear objects: displayName is null, the name lives in customMakeModel,
# make/model are generic placeholders, distance is NOT here (see stats below).
FILTER_GEAR = [
    {
        "uuid": "aaa",
        "displayName": None,
        "customMakeModel": "Saucony Guide 18",
        "gearMakeName": "Other",
        "gearModelName": "Unknown Shoes",
        "gearTypeName": "Shoes",
        "gearStatusName": "active",
        "maximumMeters": 1000000.0,
        "dateBegin": "2025-12-25T00:00:00.0",
        "dateEnd": None,
    },
]

GEAR_STATS = {"uuid": "aaa", "totalDistance": 714921.09, "totalActivities": 79}


@pytest.fixture
def client():
    c = Mock()
    c.garth.profile = {"profileId": 138658236, "displayName": "x", "fullName": "y"}
    c.get_gear.return_value = FILTER_GEAR
    c.get_gear_stats.return_value = GEAR_STATS
    return c


class TestGetGear:
    def test_merges_metadata_and_stats(self, client):
        result = api.get_gear(client, "138658236")
        assert result["count"] == 1
        g = result["gear"][0]
        assert g["uuid"] == "aaa"
        assert g["name"] == "Saucony Guide 18"          # from customMakeModel, not displayName
        assert g["type"] == "Shoes"
        assert g["status"] == "active"
        assert g["distance_km"] == 714.9                # from stats.totalDistance, /1000
        assert g["activity_count"] == 79
        assert g["max_distance_km"] == 1000.0
        assert g["wear_pct"] == 71                      # 714921 / 1000000 * 100
        assert "date_retired" not in g                  # dateEnd is None → cleaned

    def test_auto_scopes_to_authenticated_user(self, client):
        api.get_gear(client)                            # no profile id passed
        client.get_gear.assert_called_once_with("138658236")

    def test_name_falls_back_to_displayname_then_brand(self, client):
        client.get_gear.return_value = [
            {"uuid": "b", "displayName": "My Racers", "customMakeModel": "x", "gearTypeName": "Shoes"},
            {"uuid": "c", "gearMakeName": "Nike", "gearModelName": "Pegasus 41", "gearTypeName": "Shoes"},
        ]
        client.get_gear_stats.return_value = {}
        names = {g["uuid"]: g.get("name") for g in api.get_gear(client)["gear"]}
        assert names["b"] == "My Racers"                # displayName wins
        assert names["c"] == "Nike Pegasus 41"          # brand + model when no custom name

    def test_survives_stats_endpoint_failure(self, client):
        client.get_gear_stats.side_effect = Exception("404 retired gear")
        g = api.get_gear(client)["gear"][0]
        assert g["name"] == "Saucony Guide 18"          # metadata still returned
        assert "distance_km" not in g                   # no stats → field cleaned, no crash

    def test_empty_gear_list(self, client):
        client.get_gear.return_value = []
        assert api.get_gear(client) == {"count": 0, "gear": []}

    def test_missing_profile_id_returns_error(self, client):
        client.garth.profile = {}
        assert "error" in api.get_gear(client)
