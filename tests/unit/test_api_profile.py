"""Unit tests for garmin_mcp.api.profile — curation logic with mock client."""

import pytest
from unittest.mock import Mock
from garmin_mcp.api import profile as api


@pytest.fixture
def client():
    return Mock()


class TestGetFullName:
    def test_returns_name(self, client):
        client.get_full_name.return_value = "Jean Dupont"
        assert api.get_full_name(client) == "Jean Dupont"

    def test_fallback_to_profile_api(self, client):
        client.get_full_name.return_value = None
        client.garth.connectapi.return_value = {"fullName": "Jean Dupont"}
        assert api.get_full_name(client) == "Jean Dupont"

    def test_unknown_when_all_fail(self, client):
        client.get_full_name.return_value = None
        client.garth.connectapi.side_effect = Exception("fail")
        assert api.get_full_name(client) == "Unknown"


class TestGetUserProfile:
    def test_enriches_with_settings(self, client):
        client.get_user_profile.return_value = {
            "id": 138658236,
            "displayName": "Jean Dupont",
            "location": "Paris, France",
            "userData": {
                "weight": 75000,
                "height": 180.0,
                "birthDate": "1990-01-01",
                "gender": "MALE",
            },
        }
        client.get_unit_system.return_value = "metric"
        # Zone fallback from activity
        client.get_activities.return_value = [{"activityId": 1}]
        client.get_activity_hr_in_timezones.return_value = [
            {"zoneNumber": 1, "zoneLowBoundary": 100},
        ]
        client.get_activity_power_in_timezones.side_effect = Exception("no power")

        result = api.get_user_profile(client)

        assert result["user_profile_id"] == 138658236
        assert result["display_name"] == "Jean Dupont"
        assert result["settings"]["weight_kg"] == 75.0
        assert result["settings"]["height_cm"] == 180.0
        assert result["unit_system"] == "metric"
        # HR zones enriched from activity
        assert len(result["hr_zones"]) == 1
        assert result["hr_zones"][0]["low_bpm"] == 100

    def test_no_profile(self, client):
        client.get_user_profile.return_value = None
        result = api.get_user_profile(client)
        assert "error" in result

    def test_no_userdata_doesnt_crash(self, client):
        client.get_user_profile.return_value = {"displayName": "Test"}
        client.get_unit_system.side_effect = Exception("fail")
        client.get_activities.return_value = []

        result = api.get_user_profile(client)
        assert result["display_name"] == "Test"
        assert "settings" not in result

    def test_hr_zones_from_user_data(self, client):
        """When HR zones are in user-settings, don't fetch from activity."""
        client.get_user_profile.return_value = {
            "displayName": "Test",
            "userData": {
                "heartRateZones": [
                    {"zoneNumber": 1, "startBPM": 100, "endBPM": 120},
                    {"zoneNumber": 2, "startBPM": 120, "endBPM": 140},
                ]
            },
        }
        client.get_unit_system.return_value = None

        result = api.get_user_profile(client)
        assert len(result["hr_zones"]) == 2
        assert result["hr_zones"][0]["low_bpm"] == 100
        # Should NOT have called get_activities (fallback not needed)
        client.get_activities.assert_not_called()


class TestGetHrZones:
    def test_returns_hr_zones_from_latest_activity(self, client):
        client.get_activities.return_value = [{"activityId": 12345}]
        client.get_activity_hr_in_timezones.return_value = [
            {"zoneNumber": 1, "secsInZone": 600, "zoneLowBoundary": 100},
            {"zoneNumber": 2, "secsInZone": 900, "zoneLowBoundary": 130},
            {"zoneNumber": 3, "secsInZone": 300, "zoneLowBoundary": 150},
            {"zoneNumber": 4, "secsInZone": 120, "zoneLowBoundary": 165},
            {"zoneNumber": 5, "secsInZone": 60, "zoneLowBoundary": 180},
        ]
        client.get_activity_power_in_timezones.side_effect = Exception("no power")

        result = api.get_hr_zones(client)

        assert len(result["hr_zones"]) == 5
        assert result["hr_zones"][0] == {"zone": 1, "low_bpm": 100}
        assert result["hr_zones"][4] == {"zone": 5, "low_bpm": 180}
        assert "power_zones" not in result

    def test_returns_power_zones_too(self, client):
        client.get_activities.return_value = [{"activityId": 99}]
        client.get_activity_hr_in_timezones.return_value = [
            {"zoneNumber": 1, "secsInZone": 600, "zoneLowBoundary": 100},
        ]
        client.get_activity_power_in_timezones.return_value = [
            {"zoneNumber": 1, "zoneLowBoundary": 50},
            {"zoneNumber": 2, "zoneLowBoundary": 120},
        ]

        result = api.get_hr_zones(client)

        assert len(result["hr_zones"]) == 1
        assert len(result["power_zones"]) == 2
        assert result["power_zones"][1] == {"zone": 2, "low_watts": 120}

    def test_no_activities(self, client):
        client.get_activities.return_value = []
        result = api.get_hr_zones(client)
        assert "error" in result

    def test_no_zone_data(self, client):
        client.get_activities.return_value = [{"activityId": 12345}]
        client.get_activity_hr_in_timezones.return_value = None
        client.get_activity_power_in_timezones.return_value = None

        result = api.get_hr_zones(client)
        assert "error" in result


class TestGetDevices:
    def test_enriches_with_flags(self, client):
        client.get_devices.return_value = [
            {"deviceId": 1, "displayName": "Forerunner 965", "deviceStatusName": "ACTIVE"},
            {"deviceId": 2, "displayName": "Index Scale", "deviceStatusName": "ACTIVE"},
        ]
        client.get_device_last_used.return_value = {"deviceId": 1}
        client.get_primary_training_device.return_value = {"deviceId": 1}

        result = api.get_devices(client)

        assert result["count"] == 2
        assert result["devices"][0]["is_last_used"] is True
        assert result["devices"][0]["is_primary_training"] is True
        # Second device should NOT have those flags
        assert "is_last_used" not in result["devices"][1]
        assert "is_primary_training" not in result["devices"][1]

    def test_no_devices(self, client):
        client.get_devices.return_value = None
        result = api.get_devices(client)
        assert "error" in result

    def test_enrichment_failure_doesnt_crash(self, client):
        client.get_devices.return_value = [
            {"deviceId": 1, "displayName": "Forerunner 965"},
        ]
        client.get_device_last_used.side_effect = Exception("fail")
        client.get_primary_training_device.side_effect = Exception("fail")

        result = api.get_devices(client)
        assert result["count"] == 1
        assert result["devices"][0]["name"] == "Forerunner 965"
