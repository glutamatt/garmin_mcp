"""Unit tests for garmin_mcp.api.profile — curation logic with mock client."""

import pytest
from unittest.mock import Mock
from garmin_mcp.api import profile as api
from garmin_mcp.api.contract import Unavailable


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
    def test_settings_social_profile_and_habits(self, client):
        client.get_user_profile.return_value = {
            "id": 1,
            "userData": {
                "gender": "MALE", "weight": 68700.0, "height": 171.0, "birthDate": "1984-01-02",
                "measurementSystem": "metric", "vo2MaxRunning": 50.0, "lactateThresholdHeartRate": None,
                "availableTrainingDays": ["WEDNESDAY", "TUESDAY", "SUNDAY"],
                "preferredLongTrainingDays": ["SUNDAY", "SATURDAY"],
            },
            "userSleep": {"sleepTime": 79200, "wakeTime": 25200},
        }
        client.connectapi.return_value = {"fullName": "Jane Runner", "location": "Somewhere", "displayName": "x-uuid"}
        assert api.get_user_profile(client) == {
            "name": "Jane Runner", "location": "Somewhere", "birth_date": "1984-01-02", "gender": "MALE",
            "weight_kg": 68.7, "height_cm": 171.0, "vo2_max_running": 50.0,
            "usual_bedtime": "22:00", "usual_wake_time": "07:00",
            "training_days": ["tuesday", "wednesday", "sunday"], "long_run_days": ["saturday", "sunday"],
            "measurement_system": "metric",
        }
        client.connectapi.assert_called_once_with("/userprofile-service/socialProfile")

    def test_no_profile_fails(self, client):
        client.get_user_profile.return_value = None
        with pytest.raises(Unavailable):
            api.get_user_profile(client)


class TestGetHrZones:
    @staticmethod
    def _answers(hr, power):
        return lambda path: hr if path == "/biometric-service/heartRateZones" else power

    def test_zones_per_sport_with_their_bounds(self, client):
        client.connectapi.side_effect = self._answers(
            [{"trainingMethod": "HR_RESERVE", "restingHeartRateUsed": 58, "lactateThresholdHeartRateUsed": None,
              "zone1Floor": 132, "zone2Floor": 146, "zone3Floor": 161, "zone4Floor": 176, "zone5Floor": 190,
              "maxHeartRateUsed": 205, "sport": "DEFAULT"}],
            [{"sport": "RUNNING", "functionalThresholdPower": 381.0, "zone1Floor": 248.0, "zone2Floor": 305.0,
              "zone3Floor": 343.0, "zone4Floor": 381.0, "zone5Floor": 438.0, "zone6Floor": 0.0, "zone7Floor": 0.0},
             {"sport": "ROWING", "functionalThresholdPower": 160.0, "zone1Floor": 0.0, "zone2Floor": 88.0}],
        )
        assert api.get_hr_zones(client) == {
            "hr_zones": [{"sport": "default", "method": "hr_reserve", "max_hr_bpm": 205, "resting_hr_bpm": 58,
                          "zones_bpm": [[132, 145], [146, 160], [161, 175], [176, 189], [190, 205]]}],
            "power_zones": [{"sport": "running", "ftp_watts": 381,
                             "zones_watts": [[248, 304], [305, 342], [343, 380], [381, 437], [438, None]]}],
        }

    def test_no_zone_data_is_unavailable(self, client):
        client.connectapi.side_effect = self._answers([], [])
        assert api.get_hr_zones(client) == {"available": False, "reason": "no_data"}


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

    def test_no_devices_is_an_empty_list(self, client):
        client.get_devices.return_value = None
        assert api.get_devices(client) == {"count": 0, "devices": []}

    def test_enrichment_failure_doesnt_crash(self, client):
        client.get_devices.return_value = [
            {"deviceId": 1, "displayName": "Forerunner 965"},
        ]
        client.get_device_last_used.side_effect = Exception("fail")
        client.get_primary_training_device.side_effect = Exception("fail")

        result = api.get_devices(client)
        assert result["count"] == 1
        assert result["devices"][0]["name"] == "Forerunner 965"
