"""Unit tests for garmin_mcp.api.training — curation logic with mock client."""

import datetime

import pytest
from unittest.mock import Mock
from garmin_mcp.api import training as api


@pytest.fixture
def client():
    return Mock()


NO_DATA_DAY = {"date": "2024-01-15", "available": False, "reason": "no_data"}


class TestGetMaxMetrics:
    def test_vo2max_and_fitness_age(self, client):
        """Garmin's shape: [{generic, cycling, heatAltitudeAcclimation}]; fitness age from its own endpoint."""
        client.get_max_metrics.return_value = [{
            "userId": 1,
            "generic": {"calendarDate": "2024-01-15", "vo2MaxValue": 50.0, "vo2MaxPreciseValue": 49.7,
                        "fitnessAge": None},
            "cycling": {"calendarDate": "2024-01-15", "vo2MaxValue": 48.0},
            "heatAltitudeAcclimation": None,
        }]
        client.get_fitnessage_data.return_value = {
            "chronologicalAge": 42, "fitnessAge": 38.923552068371144, "achievableFitnessAge": 36.267153123465285,
        }
        assert api.get_max_metrics(client, "2024-01-15") == {
            "date": "2024-01-15", "vo2_max": 50.0, "vo2_max_precise": 49.7, "cycling_vo2_max": 48.0,
            "fitness_age": 38.9, "achievable_fitness_age": 36.3, "chronological_age": 42,
        }

    def test_no_data_is_unavailable(self, client):
        client.get_max_metrics.return_value = None
        client.get_fitnessage_data.return_value = None
        assert api.get_max_metrics(client, "2024-01-15") == NO_DATA_DAY

    def test_fitness_age_failure_keeps_the_vo2max(self, client):
        from garminconnect import GarminConnectConnectionError

        client.get_max_metrics.return_value = [{"generic": {"calendarDate": "2024-01-15", "vo2MaxValue": 50.0}}]
        client.get_fitnessage_data.side_effect = GarminConnectConnectionError("404")
        assert api.get_max_metrics(client, "2024-01-15") == {"date": "2024-01-15", "vo2_max": 50.0}


class TestGetHrvData:
    def test_curates_summary(self, client):
        client.get_hrv_data.return_value = {
            "hrvSummary": {
                "calendarDate": "2024-01-15", "weeklyAvg": 28, "lastNightAvg": 35, "lastNight5MinHigh": 60,
                "baseline": {"lowUpper": 30, "balancedLow": 32, "balancedUpper": 43, "markerValue": 0.05},
                "status": "LOW", "feedbackPhrase": "HRV_LOW_5",
            },
            "hrvReadings": [{"hrvValue": 30}],
        }
        assert api.get_hrv_data(client, "2024-01-15") == {
            "date": "2024-01-15", "last_night_avg_hrv_ms": 35, "last_night_5min_high_hrv_ms": 60,
            "weekly_avg_hrv_ms": 28, "baseline_balanced_low_ms": 32, "baseline_balanced_upper_ms": 43,
            "hrv_status": "LOW", "hrv_feedback": "HRV_LOW_5",
        }

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
    def test_distance_per_sport_in_metres(self, client):
        client.get_progress_summary_between_dates.return_value = [
            {"date": "2024-01-01", "countOfActivities": 3, "stats": {
                "running": {"distance": {"count": 2, "sum": 2000000.0}},
                "cycling": {"distance": {"count": 1, "sum": 5000000.0}},
            }},
            {"date": "2024-01-08", "countOfActivities": 1, "stats": {
                "running": {"distance": {"count": 1, "sum": 1000000.0}},
            }},
        ]
        assert api.get_progress_summary(client, "2024-01-01", "2024-01-14", "distance") == {
            "metric": "distance", "from": "2024-01-01", "to": "2024-01-14", "activity_count": 4, "count": 2,
            "sports": [
                {"sport": "cycling", "activity_count": 1, "total_distance_m": 50000, "avg_distance_m": 50000},
                {"sport": "running", "activity_count": 3, "total_distance_m": 30000, "avg_distance_m": 10000},
            ],
        }

    def test_duration_in_seconds(self, client):
        client.get_progress_summary_between_dates.return_value = [
            {"stats": {"running": {"duration": {"count": 2, "sum": 7200000.0}}}},
        ]
        [running] = api.get_progress_summary(client, "2024-01-01", "2024-01-14", "duration")["sports"]
        assert (running["total_duration_s"], running["avg_duration_s"]) == (7200, 3600)

    def test_no_data_is_an_empty_list(self, client):
        client.get_progress_summary_between_dates.return_value = []
        out = api.get_progress_summary(client, "2024-01-01", "2024-01-14", "distance")
        assert (out["count"], out["sports"]) == (0, [])


class TestGetRacePredictions:
    def test_times_in_seconds(self, client):
        client.get_race_predictions.return_value = {
            "userId": 1, "calendarDate": "2024-01-15", "time5K": 1441, "time10K": 3076,
            "timeHalfMarathon": 7006, "timeMarathon": 15702,
        }
        assert api.get_race_predictions(client) == {
            "date": "2024-01-15", "race_5k_s": 1441, "race_10k_s": 3076,
            "race_half_marathon_s": 7006, "race_marathon_s": 15702,
        }

    def test_no_data_is_unavailable(self, client):
        client.get_race_predictions.return_value = None
        assert api.get_race_predictions(client) == {"available": False, "reason": "no_data"}


class TestGetGoals:
    def test_returns_data(self, client):
        client.get_goals.return_value = [{"goalId": 1}]
        assert api.get_goals(client) == {"count": 1, "goals": [{"goalId": 1}]}

    def test_no_data_is_an_empty_list(self, client):
        client.get_goals.return_value = None
        assert api.get_goals(client) == {"count": 0, "goals": []}


class TestGetPersonalRecords:
    def test_record_value_unit_date_activity(self, client):
        client.get_personal_record.return_value = [
            {"typeId": 3, "activityId": 11, "activityName": "Morning Run", "activityType": "running",
             "activityStartDateTimeLocalFormatted": "2024-06-09T14:24:12.0", "value": 1421.052001953125,
             "prStartTimeGmtFormatted": "2024-06-09T12:35:39.0", "status": "ACCEPTED"},
            {"typeId": 8, "activityId": 12, "activityName": "Long Ride", "activityType": "cycling",
             "activityStartDateTimeLocalFormatted": "2024-06-28T08:29:04.0", "value": 80981.14},
            {"typeId": 99, "activityId": 13, "activityStartDateTimeLocalFormatted": "2024-07-01T08:00:00.0",
             "value": 4.5},
        ]
        assert api.get_personal_records(client) == {"count": 3, "records": [
            {"record": "run_5k", "value_s": 1421, "date": "2024-06-09", "activity_id": 11,
             "activity_name": "Morning Run", "sport": "running"},
            {"record": "ride_longest", "value_m": 80981, "date": "2024-06-28", "activity_id": 12,
             "activity_name": "Long Ride", "sport": "cycling"},
            # an unknown record keeps Garmin's value, without a unit
            {"record": "type_99", "value": 4.5, "date": "2024-07-01", "activity_id": 13},
        ]}


class TestGetLactateThreshold:
    def test_threshold_and_ftp(self, client):
        client.get_lactate_threshold.return_value = {
            "speed_and_heart_rate": {"calendarDate": "2024-01-10", "speed": 0.33, "heartRate": 172},
            "power": {"functionalThresholdPower": 381, "powerToWeight": 5.5458, "ftpCreateTime": "2024-01-02T05:01:47.580"},
        }
        assert api.get_lactate_threshold(client) == {
            "lactate_threshold_hr_bpm": 172, "lactate_threshold_date": "2024-01-10",
            "ftp_watts": 381, "power_to_weight": 5.55, "ftp_date": "2024-01-02T05:01:47",
        }

    def test_ftp_only_says_why_there_is_no_threshold(self, client):
        """Forerunner 165: a running FTP, no lactate threshold."""
        client.get_lactate_threshold.return_value = {
            "speed_and_heart_rate": {"speed": None, "heartRate": None},
            "power": {"functionalThresholdPower": 381, "powerToWeight": 5.5458},
        }
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {"hasRunningLactateThresholdCapableDevice": False}}
        out = api.get_lactate_threshold(client)
        assert out["ftp_watts"] == 381
        assert out["empty_fields"] == {"lactate_threshold_hr_bpm": "not_supported_by_device"}


class TestGetEnduranceScore:
    def test_score_class_and_weekly_means(self, client):
        client.get_endurance_score.return_value = {
            "groupMap": {"2024-04-23": {"groupAverage": 8499, "groupMax": 8578},
                         "2024-04-16": {"groupAverage": 8614, "groupMax": 8649}},
            "enduranceScoreDTO": {
                "calendarDate": "2024-07-08", "overallScore": 8587, "classification": 6,
                "classificationLowerLimitIntermediate": 5100, "classificationLowerLimitTrained": 5800,
                "classificationLowerLimitWellTrained": 6600, "classificationLowerLimitExpert": 7300,
                "classificationLowerLimitSuperior": 8100, "classificationLowerLimitElite": 8800,
            },
        }
        out = api.get_endurance_score(client, "2024-07-08", 12)
        client.get_endurance_score.assert_called_once_with("2024-04-15", "2024-07-08")
        assert out["endurance_score"] == 8587
        assert out["endurance_class"] == "superior"
        assert out["endurance_class_limits"]["elite"] == 8800
        assert out["weekly"] == [{"week": "2024-04-16", "avg": 8614, "max": 8649},
                                 {"week": "2024-04-23", "avg": 8499, "max": 8578}]

    def test_not_computed_by_the_device(self, client):
        client.get_endurance_score.return_value = {"groupMap": {"2024-07-01": {"groupAverage": None}},
                                                   "enduranceScoreDTO": None}
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {"hasHillScoreAndEnduranceScoreCapableDevice": False}}
        assert api.get_endurance_score(client, "2024-07-08", 12) == {
            "date": "2024-07-08", "available": False, "reason": "not_supported_by_device"}


class TestGetHillScore:
    def test_scores_per_day(self, client):
        client.get_hill_score.return_value = {"hillScoreDTOList": [
            {"calendarDate": "2024-07-08", "overallScore": 61, "strengthScore": 55, "enduranceScore": 64},
        ]}
        assert api.get_hill_score(client, "2024-07-01", "2024-07-08") == {
            "from": "2024-07-01", "to": "2024-07-08", "count": 1, "days": [
                {"date": "2024-07-08", "hill_score": 61, "hill_strength_score": 55, "hill_endurance_score": 64}]}

    def test_not_computed_by_the_device(self, client):
        client.get_hill_score.return_value = {"hillScoreDTOList": []}
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {"hasHillScoreAndEnduranceScoreCapableDevice": False}}
        assert api.get_hill_score(client, "2024-07-01", "2024-07-08") == {
            "from": "2024-07-01", "to": "2024-07-08", "available": False, "reason": "not_supported_by_device"}


def _activity(activity_id, start_local, duration_s, load=None, rpe=None):
    """A list item (`get_activities_by_date`) and, for its detail, the RPE as Garmin stores it (×10)."""
    item = {"activityId": activity_id, "startTimeLocal": start_local, "duration": duration_s,
            "activityType": {"typeKey": "running"}}
    if load is not None:
        item["activityTrainingLoad"] = load
    detail = {"activityId": activity_id, "summaryDTO": {} if rpe is None else {"directWorkoutRpe": rpe * 10}}
    return item, detail


def _with_activities(client, *activities):
    items = [item for item, _ in activities]
    details = {item["activityId"]: detail for item, detail in activities}
    client.get_activities_by_date.return_value = items
    client.get_activity.side_effect = lambda activity_id: details[activity_id]


class TestGetTrainingLoad:
    def test_foster_and_acwr_from_session_rpe(self, client):
        """sRPE = RPE × minutes, summed per local day; 4 weeks to the date."""
        _with_activities(
            client,
            _activity(1, "2026-09-10 08:00:00", 3600, rpe=5),   # week 1: 300
            _activity(2, "2026-09-29 07:00:00", 1800, rpe=4),   # last week: 120
            _activity(3, "2026-10-01 18:00:00", 2400, rpe=6),   # 240
            _activity(4, "2026-10-01 07:00:00", 600, rpe=3),    # same day: 30
        )
        out = api.get_training_load(client, "2026-10-05")
        client.get_activities_by_date.assert_called_once_with("2026-09-08", "2026-10-05", "")
        assert out["from"] == "2026-09-08"
        assert (out["load"], out["unit"]) == ("srpe", "RPE × min")
        assert out["week_load"] == 390
        assert out["chronic_week_load"] == 100  # the 3 weeks before: 300 / 3
        assert out["acwr"] == 3.9
        # last 7 days: 120, 0, 270, 0, 0, 0, 0 → mean 55.7, population SD 96.1
        assert [d["load"] for d in out["last_7_days"]] == [120, 0, 270, 0, 0, 0, 0]
        assert out["monotony"] == 0.58
        assert out["strain"] == 226
        assert [w["load"] for w in out["weeks"]] == [300, 0, 0, 390]
        assert out["weeks"][0] == {"from": "2026-09-08", "to": "2026-09-14", "load": 300}
        assert out["activities"] == 4
        assert "load_missing" not in out

    def test_activity_without_rpe_counts_as_zero_and_is_listed(self, client):
        _with_activities(client, _activity(1, "2026-10-01 08:00:00", 3600, rpe=5),
                         _activity(2, "2026-10-02 08:00:00", 3600))
        out = api.get_training_load(client, "2026-10-05")
        assert out["week_load"] == 300
        assert out["load_missing"] == {"2": "no_data"}

    def test_epoc_reads_the_list_only(self, client):
        _with_activities(client, _activity(1, "2026-10-01 08:00:00", 3600, load=85.4),
                         _activity(2, "2026-10-03 08:00:00", 3600, load=40.0))
        out = api.get_training_load(client, "2026-10-05", "epoc")
        client.get_activity.assert_not_called()
        assert (out["week_load"], out["unit"]) == (125, "EPOC")

    def test_acwr_is_uncoupled(self, client):
        """The last week's load is not in the chronic load: no load before it → no ACWR."""
        _with_activities(client, _activity(1, "2026-10-01 08:00:00", 3600, rpe=5))
        out = api.get_training_load(client, "2026-10-05")
        assert (out["week_load"], out["chronic_week_load"], out["acwr"]) == (300, 0, None)

    def test_same_load_every_day_has_no_monotony(self, client):
        _with_activities(client)
        out = api.get_training_load(client, "2026-10-05")
        assert (out["week_load"], out["acwr"], out["monotony"], out["strain"]) == (0, None, None, None)

    def test_a_watch_without_epoc_is_not_supported(self, client):
        _with_activities(client, _activity(1, "2026-10-01 08:00:00", 3600))
        client.get_usage_indicators.return_value = {
            "deviceBasedIndicators": {"hasAcuteTrainingLoadCapableDevice": False}}
        assert api.get_training_load(client, "2026-10-05", "epoc") == {
            "from": "2026-09-08", "to": "2026-10-05", "load": "epoc", "activities": 1,
            "available": False, "reason": "not_supported_by_device",
        }

    def test_no_rpe_at_all_is_no_data(self, client):
        _with_activities(client, _activity(1, "2026-10-01 08:00:00", 3600))
        out = api.get_training_load(client, "2026-10-05")
        assert (out["available"], out["reason"]) == (False, "no_data")

    @pytest.mark.parametrize("date, source", [("2026-13-01", "srpe"), ("2026-10-05", "trimp")])
    def test_invalid_input(self, client, date, source):
        from garmin_mcp.api.contract import InvalidInput

        with pytest.raises(InvalidInput):
            api.get_training_load(client, date, source)
        client.get_activities_by_date.assert_not_called()


class TestTrainingLoadPlan:
    """`--plan`: sessions to come, as minutes × RPE on their day."""

    def test_plan_adds_srpe_to_its_day_and_is_marked(self, client):
        _with_activities(client, _activity(1, "2026-09-10 08:00:00", 3600, rpe=5),   # 300, chronic
                         _activity(2, "2026-10-01 08:00:00", 1800, rpe=4))           # 120, done
        plan = api.parse_plan("2026-10-04:60:7,2026-10-05:40:3")                    # 420 + 120
        out = api.get_training_load(client, "2026-10-05", plan=plan)
        assert out["week_load"] == 660
        assert out["chronic_week_load"] == 100
        assert (out["acwr"], out["acwr_zone"]) == (6.6, "very_high")
        assert out["planned_load"] == 540
        assert out["last_7_days"][-3:] == [
            {"date": "2026-10-03", "load": 0},
            {"date": "2026-10-04", "load": 420, "planned": 420},
            {"date": "2026-10-05", "load": 120, "planned": 120},
        ]
        assert out["weeks"][-1] == {"from": "2026-09-29", "to": "2026-10-05", "load": 660, "planned": 540}
        assert "planned" not in out["weeks"][0]
        assert out["activities"] == 2

    def test_projection_equals_the_value_of_the_day_once_the_plan_is_done(self, client):
        """Same formula: a planned session counts like the same session done."""
        done = [_activity(1, "2026-09-12 08:00:00", 3600, rpe=5), _activity(2, "2026-10-01 08:00:00", 2400, rpe=6)]
        _with_activities(client, *done, _activity(3, "2026-10-04 08:00:00", 3000, rpe=7))
        real = api.get_training_load(client, "2026-10-05")
        _with_activities(client, *done)
        projected = api.get_training_load(client, "2026-10-05", plan=api.parse_plan("2026-10-04:50:7"))
        for key in ("week_load", "chronic_week_load", "acwr", "acwr_zone", "monotony", "strain", "weeks"):
            assert _without_planned(projected[key]) == real[key], key

    def test_without_plan_no_planned_key(self, client):
        _with_activities(client, _activity(1, "2026-10-01 08:00:00", 3600, rpe=5))
        out = api.get_training_load(client, "2026-10-05")
        assert "planned_load" not in out
        assert all("planned" not in d for d in out["last_7_days"] + out["weeks"])

    def test_plan_with_epoc_is_refused_before_any_call(self, client):
        from garmin_mcp.api.contract import InvalidInput

        with pytest.raises(InvalidInput, match="EPOC"):
            api.get_training_load(client, "2026-10-05", "epoc", api.parse_plan("2026-10-04:60:7"))
        client.get_activities_by_date.assert_not_called()

    def test_plan_outside_the_window_is_refused(self, client):
        from garmin_mcp.api.contract import InvalidInput

        with pytest.raises(InvalidInput, match="2026-10-06 is outside the 4 weeks 2026-09-08 → 2026-10-05"):
            api.get_training_load(client, "2026-10-05", plan=api.parse_plan("2026-10-06:60:7"))
        client.get_activities_by_date.assert_not_called()

    def test_parse(self):
        assert api.parse_plan(" 2026-11-01:60:7 , 2026-11-02:42.5:3.5") == [
            api.PlannedSession(datetime.date(2026, 11, 1), 60.0, 7.0),
            api.PlannedSession(datetime.date(2026, 11, 2), 42.5, 3.5),
        ]

    @pytest.mark.parametrize("text", [
        "2026-11-01:60", "2026-11-01:60:7:1", "2026-13-01:60:7", "2026-11-01:soixante:7",
        "2026-11-01:0:7", "2026-11-01:1500:7", "2026-11-01:60:11", "2026-11-01:60:0", "2026-11-01:nan:7",
        "2026-11-01:60:7,", "",
    ])
    def test_parse_refuses_a_bad_entry_with_the_format(self, text):
        from garmin_mcp.api.contract import InvalidInput

        with pytest.raises(InvalidInput, match="YYYY-MM-DD:MINUTES:RPE"):
            api.parse_plan(text)


def _without_planned(value):
    """A `weeks` list without its `planned` marks (or any other value as is)."""
    if isinstance(value, list):
        return [{k: v for k, v in entry.items() if k != "planned"} for entry in value]
    return value


class TestAcwrZone:
    @pytest.mark.parametrize("acwr, zone", [
        (None, None), (0.0, "low"), (0.79, "low"), (0.8, "optimal"), (1.3, "optimal"),
        (1.31, "high"), (1.5, "high"), (1.51, "very_high"), (3.9, "very_high"),
    ])
    def test_thresholds(self, acwr, zone):
        from garmin_mcp.api.training_fields import acwr_zone

        assert acwr_zone(acwr) == zone

    def test_in_the_answer(self, client):
        _with_activities(client, _activity(1, "2026-09-10 08:00:00", 3600, rpe=5),
                         _activity(2, "2026-10-01 08:00:00", 1200, rpe=6))
        out = api.get_training_load(client, "2026-10-05")
        assert (out["acwr"], out["acwr_zone"]) == (1.2, "optimal")

    def test_no_acwr_no_zone(self, client):
        _with_activities(client, _activity(1, "2026-10-01 08:00:00", 3600, rpe=5))
        out = api.get_training_load(client, "2026-10-05")
        assert (out["acwr"], out["acwr_zone"]) == (None, None)
