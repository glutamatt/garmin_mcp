"""Unit tests for garmin_mcp.api.capabilities — device capability filtering."""

import pytest
from unittest.mock import Mock
from garmin_mcp.api import capabilities as api


@pytest.fixture
def client():
    return Mock()


class TestGetDeviceCapabilities:
    def test_all_capable(self, client):
        """Device with all capabilities returns no disabled tools."""
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {
                "hasTrainingStatusCapableDevice": True,
                "hasHrvStatusCapableDevice": True,
                "hasBodyBatteryCapableDevice": True,
                "hasVO2MaxRunCapable": True,
                "hasSleepScoreCapableDevice": True,
                "hasRespirationCapableDevice": True,
                "hasSpO2CapableDevice": True,
                "hasStressCapableDevice": True,
            }
        }
        result = api.get_device_capabilities(client)

        assert result["disabled_tools"] == []
        assert result["capabilities"]["hasHrvStatusCapableDevice"] is True
        assert result["capabilities"]["hasBodyBatteryCapableDevice"] is True

    def test_some_disabled(self, client):
        """Device without HRV and body battery disables those tools."""
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {
                "hasTrainingStatusCapableDevice": True,
                "hasHrvStatusCapableDevice": False,
                "hasBodyBatteryCapableDevice": False,
                "hasVO2MaxRunCapable": True,
                "hasSleepScoreCapableDevice": True,
                "hasRespirationCapableDevice": True,
                "hasSpO2CapableDevice": True,
                "hasStressCapableDevice": True,
            }
        }
        result = api.get_device_capabilities(client)

        assert "get_hrv_data" in result["disabled_tools"]
        assert "get_body_battery" in result["disabled_tools"]
        assert result["capabilities"]["hasHrvStatusCapableDevice"] is False

    def test_unknown_flags_default_true(self, client):
        """Missing flags default to True (fail-open)."""
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {}
        }
        result = api.get_device_capabilities(client)

        assert result["disabled_tools"] == []
        # All capabilities should default to True
        for flag, value in result["capabilities"].items():
            assert value is True, f"{flag} should default to True"

    def test_api_failure_returns_empty(self, client):
        """If the API call fails, return empty (fail-open)."""
        client.get_usage_indicators.side_effect = Exception("Network error")
        result = api.get_device_capabilities(client)

        assert result["capabilities"] == {}
        assert result["disabled_tools"] == []

    def test_no_indicators_key(self, client):
        """If deviceBasedIndicators is missing, return empty."""
        client.get_usage_indicators.return_value = {}
        result = api.get_device_capabilities(client)

        assert result["disabled_tools"] == []

    def test_disabled_tools_sorted(self, client):
        """Disabled tools list is sorted alphabetically."""
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {
                "hasHrvStatusCapableDevice": False,
                "hasBodyBatteryCapableDevice": False,
                "hasSpO2CapableDevice": False,
            }
        }
        result = api.get_device_capabilities(client)

        assert result["disabled_tools"] == sorted(result["disabled_tools"])

    def test_multiple_flags_same_tool(self, client):
        """A tool disabled by multiple flags only appears once."""
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {
                "hasTrainingStatusCapableDevice": False,
                "hasTrainingEffectCapableDevice": False,
                "hasTrainingLoadCapableDevice": False,
            }
        }
        result = api.get_device_capabilities(client)

        # get_training_status is in all three, should appear only once
        assert result["disabled_tools"].count("get_training_status") == 1

    def test_basic_device_many_disabled(self, client):
        """A basic device (Instinct style) with limited features."""
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {
                "hasTrainingStatusCapableDevice": False,
                "hasHrvStatusCapableDevice": False,
                "hasBodyBatteryCapableDevice": False,
                "hasVO2MaxRunCapable": False,
                "hasSleepScoreCapableDevice": False,
                "hasRespirationCapableDevice": False,
                "hasSpO2CapableDevice": False,
                "hasStressCapableDevice": False,
                "hasFitnessAgeCapableDevice": False,
                "hasWomenHealthCapableDevice": False,
            }
        }
        result = api.get_device_capabilities(client)

        # Should have many disabled tools
        assert len(result["disabled_tools"]) > 5
        assert "get_hrv_data" in result["disabled_tools"]
        assert "get_body_battery" in result["disabled_tools"]
        assert "get_sleep" in result["disabled_tools"]
        assert "get_stress" in result["disabled_tools"]

    def test_non_dict_indicators_returns_empty(self, client):
        """If deviceBasedIndicators is not a dict, return empty."""
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": "unexpected"
        }
        result = api.get_device_capabilities(client)

        assert result["capabilities"] == {}
        assert result["disabled_tools"] == []


# ── Why an answer has no data ────────────────────────────────────────────────


def _flags(**flags):
    return {"deviceBasedIndicators": flags}


class TestMissingReason:
    @pytest.mark.parametrize("feature, flag", sorted(api.FEATURE_FLAGS.items()))
    def test_a_false_flag_is_not_supported_by_device(self, client, feature, flag):
        client.get_usage_indicators.return_value = _flags(**{flag: False})
        assert api.missing_reason(client, feature) == "not_supported_by_device"

    @pytest.mark.parametrize("feature, flag", sorted(api.FEATURE_FLAGS.items()))
    def test_a_true_flag_is_no_data(self, client, feature, flag):
        client.get_usage_indicators.return_value = _flags(**{flag: True})
        assert api.missing_reason(client, feature) == "no_data"

    @pytest.mark.parametrize("indicators", [{}, _flags(), {"deviceBasedIndicators": "unexpected"}, None])
    def test_an_unknown_flag_is_no_data(self, client, indicators):
        client.get_usage_indicators.return_value = indicators
        assert api.missing_reason(client, api.TRAINING_STATUS) == "no_data"

    def test_flags_not_read_is_no_data(self, client):
        """The answer stays true: `no_data`, only less precise."""
        client.get_usage_indicators.side_effect = Exception("Network error")
        assert api.missing_reason(client, api.TRAINING_STATUS) == "no_data"

    def test_feature_flags_are_garmin_flags(self):
        """Names seen in Garmin's `deviceBasedIndicators` answer (02/10/2026)."""
        assert api.FEATURE_FLAGS == {
            "training_readiness": "hasTrainingReadinessCapableDevice",
            "training_status": "hasTrainingStatusCapableDevice",
            "training_load": "hasAcuteTrainingLoadCapableDevice",
        }


class TestDayAnswer:
    def test_data_is_the_answer_and_reads_no_flag(self, client):
        curated = {"date": "2024-01-15", "score": 70}
        assert api.day_answer(client, api.TRAINING_READINESS, "2024-01-15", curated) is curated
        client.get_usage_indicators.assert_not_called()

    @pytest.mark.parametrize("curated", [None, {}, {"date": "2024-01-15"}])
    def test_no_data_says_why(self, client, curated):
        client.get_usage_indicators.return_value = _flags(hasTrainingReadinessCapableDevice=False)
        assert api.day_answer(client, api.TRAINING_READINESS, "2024-01-15", curated) == {
            "date": "2024-01-15", "available": False, "reason": "not_supported_by_device",
        }
