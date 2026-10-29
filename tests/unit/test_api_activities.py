"""Unit tests for garmin_mcp.api.activities — curation logic with mock client."""

import csv
import io
import zipfile
from datetime import datetime
from types import SimpleNamespace

import pytest
from unittest.mock import Mock, patch
from garmin_mcp.api import activities as api
from garmin_mcp.api.contract import AuthError, InvalidInput, NotFound, Unavailable


@pytest.fixture
def client():
    c = Mock()
    c.get_activity_typed_splits.return_value = {"splits": []}
    return c


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
        assert a["sport"] == "running"
        assert a["distance_m"] == 10000
        assert a["start_time"] == "2024-01-15T07:00:00"
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

    def test_no_data_pagination_is_an_empty_list(self, client):
        client.get_activities.return_value = []
        result = api.get_activities(client)
        assert result["count"] == 0
        assert result["activities"] == []
        assert result["has_more"] is False

    def test_limit_capped(self, client):
        client.get_activities.return_value = []
        api.get_activities(client, limit=999)
        client.get_activities.assert_called_with(0, 100, None)


class TestTrainingLoad:
    def test_read_from_the_list_item(self, client):
        """The list endpoint has `activityTrainingLoad` when the device computes it."""
        client.get_activities_by_date.return_value = [{**SAMPLE_RAW_ACTIVITY, "activityTrainingLoad": 142.46}]
        result = api.get_activities(client, "2024-01-01", "2024-01-15")
        assert result["activities"][0]["training_load"] == 142.5

    @pytest.mark.parametrize("call", [
        lambda client: api.get_activities(client, "2024-01-01", "2024-01-15"),
        lambda client: api.get_activities(client, start=0, limit=5),
    ])
    def test_no_graphql_call(self, call):
        """The GraphQL list (`activitiesScalar`) has the same items as the REST list: never asked."""
        client = Mock()
        client.get_activities_by_date.return_value = [SAMPLE_RAW_ACTIVITY]
        client.get_activities.return_value = [SAMPLE_RAW_ACTIVITY]
        call(client)
        client.query_garmin_graphql.assert_not_called()


def _detail(rpe=None, feel=None) -> dict:
    summary = {"distance": 10000.0}
    if rpe is not None:
        summary["directWorkoutRpe"] = rpe
    if feel is not None:
        summary["directWorkoutFeel"] = feel
    return {"activityId": 12345, "summaryDTO": summary}


class TestWithEffort:
    def _list(self, client, *ids):
        client.get_activities_by_date.return_value = [{**SAMPLE_RAW_ACTIVITY, "activityId": i} for i in ids]

    def test_adds_rpe_and_feel_from_each_detail(self, client):
        self._list(client, 1, 2)
        client.get_activity.side_effect = lambda i: _detail(rpe=30 if i == 1 else 70, feel=50)
        result = api.get_activities(client, "2024-01-01", "2024-01-15", with_effort=True)
        assert [(a["id"], a["perceived_effort"], a["workout_feel"]) for a in result["activities"]] == [
            (1, 3.0, 50), (2, 7.0, 50),
        ]
        assert "effort_missing" not in result
        assert sorted(c.args[0] for c in client.get_activity.call_args_list) == [1, 2]

    def test_says_which_activities_have_no_rpe(self, client):
        self._list(client, 1, 2)
        client.get_activity.side_effect = lambda i: _detail(rpe=30) if i == 1 else _detail()
        result = api.get_activities(client, "2024-01-01", "2024-01-15", with_effort=True)
        assert result["effort_missing"] == {"2": "no_data"}
        assert "perceived_effort" not in result["activities"][1]

    def test_a_failed_detail_is_named_the_others_are_kept(self, client):
        self._list(client, 1, 2)

        def detail(i):
            if i == 2:
                raise ConnectionError("reset by peer")
            return _detail(rpe=30)

        client.get_activity.side_effect = detail
        result = api.get_activities(client, "2024-01-01", "2024-01-15", with_effort=True)
        assert result["activities"][0]["perceived_effort"] == 3.0
        assert result["effort_missing"]["2"].startswith("error: ")
        assert "reset by peer" in result["effort_missing"]["2"]

    def test_every_detail_failing_fails_the_list(self, client):
        self._list(client, 1, 2)
        client.get_activity.side_effect = NotFound("gone")
        with pytest.raises(NotFound):
            api.get_activities(client, "2024-01-01", "2024-01-15", with_effort=True)

    def test_an_auth_error_fails_the_list(self, client):
        self._list(client, 1, 2)

        def detail(i):
            if i == 2:
                raise AuthError("login refused")
            return _detail(rpe=30)

        client.get_activity.side_effect = detail
        with pytest.raises(AuthError):
            api.get_activities(client, "2024-01-01", "2024-01-15", with_effort=True)

    def test_list_fields_are_kept(self, client):
        self._list(client, 1)
        client.get_activity.return_value = _detail(rpe=30)
        activity = api.get_activities(client, "2024-01-01", "2024-01-15", with_effort=True)["activities"][0]
        assert activity["distance_m"] == 10000
        assert activity["start_time"] == "2024-01-15T07:00:00"
        assert "summaryDTO" not in activity

    def test_pagination_mode(self, client):
        client.get_activities.return_value = [SAMPLE_RAW_ACTIVITY]
        client.get_activity.return_value = _detail(rpe=20)
        result = api.get_activities(client, start=0, limit=5, with_effort=True)
        assert result["activities"][0]["perceived_effort"] == 2.0

    def test_empty_list_makes_no_detail_call(self, client):
        client.get_activities_by_date.return_value = []
        result = api.get_activities(client, "2024-01-01", "2024-01-15", with_effort=True)
        assert result["count"] == 0
        assert "effort_missing" not in result
        client.get_activity.assert_not_called()

    def test_too_many_activities_is_invalid_input(self, client):
        self._list(client, *range(api.EFFORT_MAX_ACTIVITIES + 1))
        with pytest.raises(InvalidInput, match="shorter range"):
            api.get_activities(client, "2020-01-01", "2024-01-15", with_effort=True)
        client.get_activity.assert_not_called()

    def test_without_the_option_no_detail_call(self, client):
        self._list(client, 1)
        api.get_activities(client, "2024-01-01", "2024-01-15")
        client.get_activity.assert_not_called()


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
        client.get_activity_typed_splits.return_value = {"splits": []}
        result = api.get_activity(client, 12345)
        assert result["id"] == 12345
        assert result["sport"] == "running"
        assert result["start_time"] == "2024-01-15T07:00:00"
        assert result["avg_pace_s_per_km"] == 300  # 1000 / 3.33
        assert result["training_effect"] == 3.5
        assert result["training_load"] == 85
        assert result["lap_count"] == 5
        assert "weather" not in result

    def test_relief_and_paces(self, client):
        client.get_activity.return_value = {
            "activityId": 1,
            "summaryDTO": {
                "averageSpeed": 2.39, "averageMovingSpeed": 2.4033, "avgGradeAdjustedSpeed": 2.405,
                "elevationGain": 40.0, "elevationLoss": 47.0, "minElevation": 69.8, "maxElevation": 100.8,
            },
        }
        client.get_activity_weather.return_value = None
        client.get_activity_typed_splits.return_value = {"splits": []}
        result = api.get_activity(client, 1)
        assert result["avg_pace_s_per_km"] == 418
        assert result["moving_pace_s_per_km"] == 416
        assert result["gap_s_per_km"] == 416
        assert (result["elevation_gain_m"], result["elevation_loss_m"]) == (40, 47)
        assert (result["min_elevation_m"], result["max_elevation_m"]) == (70, 101)

    def test_weather_is_converted_from_imperial(self, client):
        """Garmin's weather is °F and mph."""
        client.get_activity.return_value = {"activityId": 1, "summaryDTO": {}}
        client.get_activity_weather.return_value = {
            "temp": 70, "apparentTemp": 68, "relativeHumidity": 64, "windSpeed": 12,
            "weatherTypeDTO": {"desc": "Light Rain"},
        }
        assert api.get_activity(client, 1)["weather"] == {
            "temperature_celsius": 21.1,
            "apparent_temperature_celsius": 20.0,
            "humidity_percent": 64,
            "wind_speed_mps": 5.4,
            "weather_type": "Light Rain",
        }

    def test_weather_failure_keeps_the_detail(self, client):
        client.get_activity.return_value = {"activityId": 1, "summaryDTO": {"distance": 5000.0}}
        client.get_activity_weather.side_effect = Exception("weather down")
        assert api.get_activity(client, 1) == {"id": 1, "distance_m": 5000}

    def test_no_data_is_not_found(self, client):
        client.get_activity.return_value = None
        with pytest.raises(NotFound, match="99999"):
            api.get_activity(client, 99999)


class TestGetActivitySplits:
    DETAIL = {"summaryDTO": {"startTimeLocal": "2024-01-15T08:00:00.0", "startTimeGMT": "2024-01-15T07:00:00.0"}}

    def test_curates_laps(self, client):
        client.get_activity_splits.return_value = {
            "activityId": 12345,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "startTimeGMT": "2024-01-15T07:00:00.0",
                    "distance": 1000.4,
                    "duration": 300.0,
                    "averageSpeed": 3.33,
                    "avgGradeAdjustedSpeed": 3.2,
                    "elevationGain": 12.0,
                    "averageHR": 145,
                    "maxHR": 155,
                    "wktStepIndex": 0,
                    "intensityType": "WARMUP",
                },
                {
                    "lapIndex": 2,
                    "startTimeGMT": "2024-01-15T07:05:00.0",
                    "distance": 1000.0,
                    "duration": 280.0,
                    "averageSpeed": 3.57,
                    "averageHR": 160,
                    "maxHR": 170,
                },
            ],
        }
        client.get_activity.return_value = self.DETAIL
        result = api.get_activity_splits(client, 12345)
        assert result["lap_count"] == 2
        first, second = result["laps"]
        assert first == {
            "lap_number": 1,
            "intensity_type": "WARMUP",
            "workout_step_index": 0,
            "start_time": "2024-01-15T08:00:00",
            "start_time_gmt": "2024-01-15T07:00:00",
            "duration_s": 300,
            "distance_m": 1000,
            "avg_pace_s_per_km": 300,
            "gap_s_per_km": 312,
            "avg_speed_mps": 3.33,
            "elevation_gain_m": 12,
            "avg_hr_bpm": 145,
            "max_hr_bpm": 155,
        }
        assert second["start_time"] == "2024-01-15T08:05:00"
        assert second["avg_hr_bpm"] == 160

    def test_start_time_stays_gmt_only_without_the_detail(self, client):
        client.get_activity_splits.return_value = {
            "lapDTOs": [{"lapIndex": 1, "startTimeGMT": "2024-01-15T07:00:00.0"}],
        }
        client.get_activity.return_value = None
        (lap,) = api.get_activity_splits(client, 12345)["laps"]
        assert lap == {"lap_number": 1, "start_time_gmt": "2024-01-15T07:00:00"}

    def test_no_splits_is_an_empty_list(self, client):
        client.get_activity_splits.return_value = None
        assert api.get_activity_splits(client, 12345) == {
            "activity_id": 12345, "lap_count": 0, "laps": [],
        }
        client.get_activity.assert_not_called()


def _step(order, step_type, target=None, one=None, two=None, zone=None):
    return {"type": "ExecutableStepDTO", "stepOrder": order, "stepType": {"stepTypeKey": step_type},
            "targetType": {"workoutTargetTypeKey": target or "no.target"},
            "targetValueOne": one, "targetValueTwo": two, "zoneNumber": zone}


# Shaped on a real run (27/10/2026, "Seuil #2 3x10"): Garmin Connect numbers the repeat
# before its steps (stepOrder 2, then 3, 4); the laps number it after them (index 3).
SEUIL_WORKOUT = {
    "workoutId": 77, "updatedDate": "2026-10-26T10:41:03.0",
    "workoutSegments": [{"workoutSteps": [
        _step(1, "warmup", "pace.zone", 2.4691358, 2.2988506),
        {"type": "RepeatGroupDTO", "stepOrder": 2, "stepType": {"stepTypeKey": "repeat"}, "numberOfIterations": 3,
         "workoutSteps": [_step(3, "interval", "heart.rate.zone", 168.0, 176.0), _step(4, "recovery")]},
        _step(5, "cooldown", "pace.zone", 2.3809524, 2.1505376),
    ]}],
}
WARMUP = {"type": "pace", "low_s_per_km": 405, "high_s_per_km": 435}
INTERVAL = {"type": "hr", "low_bpm": 168, "high_bpm": 176}
COOLDOWN = {"type": "pace", "low_s_per_km": 420, "high_s_per_km": 465}


class TestStepTargets:
    DETAIL = {"activityId": 9, "metadataDTO": {"associatedWorkoutId": 77},
              "summaryDTO": {"startTimeLocal": "2026-10-27T08:01:55.0", "startTimeGMT": "2026-10-27T07:01:55.0"}}

    def _splits(self, client, indexes, workout=SEUIL_WORKOUT, detail=None):
        client.get_activity_splits.return_value = {
            "activityId": 9, "lapDTOs": [{"lapIndex": n + 1, "wktStepIndex": i} for n, i in enumerate(indexes)]}
        client.get_activity.return_value = detail or self.DETAIL
        client.get_workout_by_id.return_value = workout
        return api.get_activity_splits(client, 9)

    def test_each_lap_has_its_step_target_through_the_repeat(self, client):
        out = self._splits(client, [0, 0, 1, 2, 1, 2, 1, 2, 4, None])
        client.get_workout_by_id.assert_called_once_with(77)
        assert [lap.get("step_target") for lap in out["laps"]] == [
            WARMUP, WARMUP, INTERVAL, {"type": "none"}, INTERVAL, {"type": "none"}, INTERVAL, {"type": "none"},
            COOLDOWN, None,
        ]
        assert "empty_fields" not in out

    def test_activity_without_workout_costs_no_call(self, client):
        out = self._splits(client, [None, None], detail={"summaryDTO": self.DETAIL["summaryDTO"]})
        client.get_workout_by_id.assert_not_called()
        assert all("step_target" not in lap for lap in out["laps"]) and "empty_fields" not in out

    def test_deleted_workout_says_why(self, client):
        client.get_workout_by_id.side_effect = NotFound("Garmin has no such object (HTTP 404)")
        out = self._splits(client, [0, 1])
        assert all("step_target" not in lap for lap in out["laps"])
        assert out["empty_fields"] == {"step_target": "workout_not_found"}

    def test_workout_saved_after_the_start_is_not_joined(self, client):
        out = self._splits(client, [0, 1], workout={**SEUIL_WORKOUT, "updatedDate": "2026-10-27T07:30:00.0"})
        assert all("step_target" not in lap for lap in out["laps"])
        assert out["empty_fields"] == {"step_target": "workout_changed_after_activity"}

    @pytest.mark.parametrize("index", [3, 5])  # the repeat itself; past the last step
    def test_a_lap_index_without_a_step_is_not_guessed(self, client, index):
        out = self._splits(client, [0, index])
        assert all("step_target" not in lap for lap in out["laps"])
        assert out["empty_fields"] == {"step_target": "workout_steps_mismatch"}

    def test_multisport_workout_is_not_joined(self, client):
        segments = SEUIL_WORKOUT["workoutSegments"] * 2
        out = self._splits(client, [0], workout={**SEUIL_WORKOUT, "workoutSegments": segments})
        assert out["empty_fields"] == {"step_target": "workout_multisport"}

    def test_garmin_unavailable_keeps_the_laps(self, client):
        client.get_workout_by_id.side_effect = Unavailable("Garmin did not answer")
        out = self._splits(client, [0])
        assert out["laps"][0]["workout_step_index"] == 0
        assert out["empty_fields"] == {"step_target": "error: Garmin did not answer"}

    def test_auth_error_fails_the_command(self, client):
        client.get_workout_by_id.side_effect = AuthError("Garmin login refused")
        with pytest.raises(AuthError):
            self._splits(client, [0])


class TestGetActivityHrInTimezones:
    def test_no_zones_is_an_empty_list(self, client):
        client.get_activity_hr_in_timezones.return_value = None
        assert api.get_activity_hr_in_timezones(client, 12345) == []


class TestDownloadActivity:
    def test_unsupported_format_is_invalid_input(self, client, tmp_path):
        with pytest.raises(InvalidInput, match="Unsupported format"):
            api.download_activity(client, 1, str(tmp_path / "a.pdf"), "pdf")
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
            api.download_activity(client, 1, str(tmp_path / "a.csv"))

    def test_fit_without_samples_is_an_empty_csv(self, client, tmp_path):
        """A manual activity has no record: an empty file and `rows: 0`, not an error."""
        client.download_activity.return_value = self._zip(["1_ACTIVITY.fit"])
        fit = Mock()
        fit.get_messages.return_value = []
        with patch("fitparse.FitFile", return_value=fit):
            result = api.download_activity(client, 1, str(tmp_path / "out" / "run.csv"))
        assert result["path"] == str(tmp_path / "out" / "run.csv")
        assert result["rows"] == 0
        assert result["columns"] == []
        assert open(result["path"]).read() == ""

    @staticmethod
    def _fit(sport: str, activity: dict | None = None) -> Mock:
        """A FIT whose one record has every field the CSV reads; `activity`: its `activity` message."""
        def message(**fields):
            return SimpleNamespace(fields=[SimpleNamespace(name=k, value=v) for k, v in fields.items()])

        record = message(
            timestamp=datetime(2026, 10, 1, 7, 0, 0), distance=1.0, heart_rate=140,
            cadence=85, fractional_cadence=0.5, enhanced_speed=3.0, enhanced_altitude=50.0,
            position_lat=580000000, position_long=27000000, temperature=18,
            vertical_oscillation=80.0, stance_time=250.0, stance_time_balance=50.1,
            step_length=1100.0, vertical_ratio=7.5, power=250,
        )
        messages = {"sport": [message(sport=sport)], "record": [record],
                    "activity": [message(**activity)] if activity else []}
        fit = Mock()
        fit.get_messages.side_effect = lambda name: messages.get(name, [])
        return fit

    @pytest.mark.parametrize("sport", ["running", "cycling"])
    def test_help_lists_every_column(self, client, tmp_path, sport):
        """`activities download --help` is the column reference: no CSV column is missing from it."""
        from garmin_mcp.cli import activities_download

        client.download_activity.return_value = self._zip(["1_ACTIVITY.fit"])
        with patch("fitparse.FitFile", return_value=self._fit(sport)):
            result = api.download_activity(client, 1, str(tmp_path / "a.csv"))
        assert len(result["columns"]) >= 16
        missing = [c for c in result["columns"] if c not in activities_download.help]
        assert missing == []

    def _first_timestamp(self, client, tmp_path, fit) -> str:
        client.download_activity.return_value = self._zip(["1_ACTIVITY.fit"])
        with patch("fitparse.FitFile", return_value=fit):
            result = api.download_activity(client, 1, str(tmp_path / "a.csv"))
        with open(result["path"]) as f:
            return next(csv.DictReader(f))["timestamp"]

    def test_timestamp_is_the_watch_local_time(self, client, tmp_path):
        """FIT times are UTC: the `activity` message gives the watch's offset."""
        fit = self._fit("running", {"timestamp": datetime(2026, 10, 1, 8, 0, 0),
                                    "local_timestamp": datetime(2026, 10, 1, 10, 0, 0)})
        assert self._first_timestamp(client, tmp_path, fit) == "2026-10-01T09:00:00+02:00"

    def test_timestamp_without_local_time_stays_utc(self, client, tmp_path):
        assert self._first_timestamp(client, tmp_path, self._fit("running")) == "2026-10-01T07:00:00+00:00"


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


def _typed(kind, start, duration, distance, **extra):
    """One of Garmin's typed splits (same keys as a lap, plus `type`)."""
    return {"type": kind, "startTimeLocal": f"2026-04-08T08:{start:02d}:00.0",
            "startTimeGMT": f"2026-04-08T06:{start:02d}:00.0", "duration": duration,
            "distance": distance, "averageSpeed": distance / duration if duration else 0.0, **extra}


TYPED_SPLITS = {"splits": [
    _typed("INTERVAL_WARMUP", 0, 600.0, 1500.0),
    _typed("RWD_RUN", 0, 1500.0, 4000.0, averageHR=150.0),
    _typed("RWD_STAND", 25, 40.0, 5.0),
    _typed("RWD_WALK", 26, 120.0, 150.0),
    _typed("INTERVAL_ACTIVE", 10, 900.0, 2500.0),
    _typed("RWD_STAND", 28, 95.0, 8.0),
]}


class TestTypedSplits:
    def test_run_walk_segments_and_totals(self, client):
        client.get_activity_typed_splits.return_value = TYPED_SPLITS
        out = api.get_activity_splits(client, 1, "run-walk")
        assert (out["by"], out["count"]) == ("run-walk", 4)
        assert [s["split_type"] for s in out["splits"]] == ["run", "stand", "walk", "stand"]
        assert out["splits"][0] == {"split_type": "run", "start_time": "2026-04-08T08:00:00",
                                    "duration_s": 1500, "distance_m": 4000, "avg_pace_s_per_km": 375,
                                    "avg_hr_bpm": 150}
        assert out["totals"] == {
            "run": {"count": 1, "duration_s": 1500, "longest_s": 1500, "distance_m": 4000},
            "stand": {"count": 2, "duration_s": 135, "longest_s": 95, "distance_m": 13},
            "walk": {"count": 1, "duration_s": 120, "longest_s": 120, "distance_m": 150},
        }

    def test_interval_is_the_workout_steps(self, client):
        client.get_activity_typed_splits.return_value = TYPED_SPLITS
        out = api.get_activity_splits(client, 1, "interval")
        assert [(s["split_type"], s["distance_m"]) for s in out["splits"]] == [("warmup", 1500), ("active", 2500)]
        assert "totals" not in out

    def test_get_has_stops_and_walks(self, client):
        client.get_activity.return_value = {"activityId": 1, "summaryDTO": {},
                                            "metadataDTO": {"associatedWorkoutId": 77}}
        client.get_activity_weather.return_value = None
        client.get_activity_typed_splits.return_value = TYPED_SPLITS
        out = api.get_activity(client, 1)
        assert out["workout_id"] == 77
        assert out["stops"] == {"count": 2, "total_s": 135, "longest_s": 95}
        assert out["walks"] == {"count": 1, "total_s": 120, "longest_s": 120}

    def test_without_run_walk_detection_get_says_nothing_about_stops(self, client):
        client.get_activity.return_value = {"activityId": 1, "summaryDTO": {}}
        client.get_activity_weather.return_value = None
        client.get_activity_typed_splits.return_value = {"splits": [_typed("INTERVAL_ACTIVE", 0, 60.0, 100.0)]}
        assert "stops" not in api.get_activity(client, 1)

    def test_typed_splits_failure_keeps_the_detail(self, client):
        client.get_activity.return_value = {"activityId": 1, "summaryDTO": {"distance": 5000.0}}
        client.get_activity_weather.return_value = None
        client.get_activity_typed_splits.side_effect = Exception("down")
        assert api.get_activity(client, 1) == {"id": 1, "distance_m": 5000}

    def test_unknown_mode(self, client):
        with pytest.raises(InvalidInput):
            api.get_activity_splits(client, 1, "mile")


def _rows(seconds, speed=2.5, cadence=170, altitude=None, hr=150):
    """Second-by-second records like `_fit_records` gives."""
    altitude = altitude or (lambda t: 100.0)
    return [{"elapsed_s": float(t), "distance_m": round(t * speed, 1), "heart_rate": hr,
             "cadence_spm": cadence, "altitude_m": altitude(t)} for t in range(seconds)]


class TestKmSplits:
    def test_one_split_per_km_and_the_rest(self):
        splits = api._km_splits(_rows(1000))  # 2500 m at 2.5 m/s
        assert [s["km"] for s in splits] == [1, 2, 3]
        assert [s["distance_m"] for s in splits] == [1000, 1000, 498]
        assert splits[0]["duration_s"] == 400 and splits[0]["avg_pace_s_per_km"] == 400
        assert splits[0]["avg_hr_bpm"] == 150 and splits[0]["avg_cadence_spm"] == 170

    def test_elevation_ignores_noise_below_one_metre(self):
        """A steady climb of 20 m with ±0.5 m of noise: 20 m up, not 20 + the noise."""
        noisy = lambda t: 100.0 + t * 20 / 400 + (0.5 if t % 2 else -0.5)
        [first, *_] = api._km_splits(_rows(400, altitude=noisy))
        assert 19 <= first["elevation_gain_m"] <= 21
        assert first["elevation_loss_m"] <= 1

    def test_no_distance_no_split(self):
        assert api._km_splits([{"elapsed_s": 0.0, "distance_m": None}]) == []


class TestHalfCadence:
    @staticmethod
    def _fix(values):
        rows = [{"cadence_spm": v} for v in values]
        api._fix_half_cadence_glitch(rows, "cadence_spm")
        return [r["cadence_spm"] for r in rows]

    def test_a_half_value_while_running_is_doubled(self):
        assert self._fix([170] * 15 + [85] + [170] * 15)[15] == 170

    def test_a_walk_is_kept(self):
        """Walking at 105-115 spm is not a glitch: before, everything under 120 was doubled."""
        walk = [110, 105, 112, 108, 115] * 8
        assert self._fix(walk) == walk

    def test_zero_is_no_value(self):
        assert self._fix([0, 170, 170])[0] is None
