"""Unit tests for garmin_mcp.api.capabilities — device capability filtering."""

import pytest
from unittest.mock import Mock
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from garmin_mcp.api import capabilities as api
from garmin_mcp.api.contract import AuthError, GarminError, NotFound


@pytest.fixture
def client():
    return Mock()


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

    @pytest.mark.parametrize("error", [
        GarminConnectConnectionError("timeout"), GarminConnectTooManyRequestsError("429"), NotFound("gone"),
    ])
    def test_flags_garmin_does_not_give_is_no_data(self, client, error):
        """The answer stays true: `no_data`, only less precise."""
        client.get_usage_indicators.side_effect = error
        assert api.missing_reason(client, api.TRAINING_STATUS) == "no_data"

    @pytest.mark.parametrize("error, raised", [
        (GarminConnectAuthenticationError("401"), AuthError),
        (KeyError("deviceBasedIndicators"), GarminError),  # a bug: never hidden behind no_data
    ])
    def test_other_failures_are_raised(self, client, error, raised):
        client.get_usage_indicators.side_effect = error
        with pytest.raises(raised):
            api.missing_reason(client, api.TRAINING_STATUS)

    def test_feature_flags_are_garmin_flags(self):
        """Names seen in Garmin's `deviceBasedIndicators` answer (02/10 and 21/10/2026)."""
        assert api.FEATURE_FLAGS == {
            "training_readiness": "hasTrainingReadinessCapableDevice",
            "training_status": "hasTrainingStatusCapableDevice",
            "training_load": "hasAcuteTrainingLoadCapableDevice",
            "lactate_threshold": "hasRunningLactateThresholdCapableDevice",
            "endurance_score": "hasHillScoreAndEnduranceScoreCapableDevice",
            "hill_score": "hasHillScoreAndEnduranceScoreCapableDevice",
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
