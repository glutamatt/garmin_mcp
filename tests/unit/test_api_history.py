"""Unit tests for garmin_mcp.api.history — long-term time-series with mock client."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from garmin_mcp.api import history as api


# ── Utility tests ────────────────────────────────────────────────────────────


class TestDateRange:
    def test_inclusive_three_days(self):
        assert api._daterange("2026-04-13", "2026-04-15") == [
            "2026-04-13",
            "2026-04-14",
            "2026-04-15",
        ]

    def test_single_day(self):
        assert api._daterange("2026-04-15", "2026-04-15") == ["2026-04-15"]

    def test_reversed_returns_empty(self):
        assert api._daterange("2026-04-20", "2026-04-15") == []


class TestFlatten:
    def test_flat_dict(self):
        out = api._flatten({"a": 1, "b": "two", "c": None})
        assert out == {"a": 1, "b": "two", "c": None}

    def test_nested_dict_prefixed(self):
        raw = {"id": 123, "activityType": {"typeKey": "running", "parentTypeId": 1}}
        out = api._flatten(raw)
        assert out["id"] == 123
        assert out["activityType_typeKey"] == "running"
        assert out["activityType_parentTypeId"] == 1

    def test_lists_dropped(self):
        out = api._flatten({"id": 1, "splits": [{"lap": 1}]})
        assert out == {"id": 1}

    def test_nested_dicts_and_lists_skipped(self):
        raw = {"a": 1, "nested": {"b": 2, "deep": {"c": 3}, "list": [1, 2]}}
        out = api._flatten(raw)
        assert out == {"a": 1, "nested_b": 2}


# ── Sport stats (Garmin "Reports" endpoint) ─────────────────────────────────


# Fixture lifted straight from the Garmin web-UI HAR capture (condensed to 2 entries,
# a handful of metrics each) so the tests are grounded in reality.
_RUNNING_FIXTURE = [
    {
        "date": "2025-10-20",
        "countOfActivities": 4,
        "stats": {
            "running": {
                "distance": {"count": 4, "min": 305551.0, "max": 1005309.96, "avg": 504386.98, "sum": 2017547.94},
                "duration": {"count": 4, "min": 1041149.04, "max": 3495990.96, "avg": 1741860.26, "sum": 6967441.04},
                "avgHr": {"count": 4, "min": 172.0, "max": 184.0, "avg": 178.25, "sum": 713.0},
                "maxHr": {"count": 4, "min": 186.0, "max": 206.0, "avg": 197.25, "sum": 789.0},
                "avgRunCadence": {"count": 4, "min": 160.2, "max": 171.8, "avg": 168.3, "sum": 673.2},
                "maxBikeCadence": {"count": 0, "min": None, "max": None, "avg": None, "sum": 0.0},
                "splitSummaries": {"doc_count": 10, "CLIMB_REST": {"doc_count": 0}},
            }
        },
    },
    {
        "date": "2025-10-27",
        "countOfActivities": 5,
        "stats": {
            "running": {
                "distance": {"count": 5, "min": 235341.99, "max": 1225142.96, "avg": 795579.80, "sum": 3977899.02},
                "avgHr": {"count": 5, "min": 154.0, "max": 179.0, "avg": 167.0, "sum": 835.0},
            }
        },
    },
]


class TestGetSportStatsRunning:
    def test_http_call_shape(self):
        client = Mock()
        client.connectapi.return_value = []
        api.get_sport_stats(client, "running", "2025-04-16", "2026-04-15")
        assert client.connectapi.call_count == 1
        args, kwargs = client.connectapi.call_args
        assert args[0] == "/fitnessstats-service/activity"
        p = kwargs["params"]
        assert p["activityType"] == "running"
        assert p["aggregation"] == "weekly"
        assert p["groupByParentActivityType"] == "true"
        assert p["startDate"] == "2025-04-16"
        assert p["endDate"] == "2026-04-15"
        assert p["standardizedUnits"] == "false"
        assert p["userFirstDay"] == "monday"
        # metric is a list → requests serializes as repeated params.
        # We send the exact 35-metric list Garmin's web UI sends (verbatim);
        # the server filters down to what's populated for the sport.
        assert isinstance(p["metric"], list)
        assert len(p["metric"]) == 35
        assert "distance" in p["metric"]
        assert "avgRunCadence" in p["metric"]
        assert "avgBikeCadence" in p["metric"]  # sent regardless of sport filter

    def test_flattens_metric_5tuples(self):
        client = Mock()
        client.connectapi.return_value = _RUNNING_FIXTURE
        rows = api.get_sport_stats(client, "running", "2025-10-20", "2025-10-27")
        assert len(rows) == 2
        r = rows[0]
        assert r["date"] == "2025-10-20"
        assert r["countOfActivities"] == 4
        # 5-tuple flattened to _count, _min, _max, _avg, _sum
        assert r["distance_count"] == 4
        assert r["distance_min"] == 305551.0
        assert r["distance_max"] == 1005309.96
        assert r["distance_avg"] == 504386.98
        assert r["distance_sum"] == 2017547.94
        assert r["avgHr_avg"] == 178.25
        assert r["maxHr_max"] == 206.0
        assert r["avgRunCadence_avg"] == 168.3
        # Empty metrics still produce columns (with null values)
        assert r["maxBikeCadence_count"] == 0
        assert r["maxBikeCadence_avg"] is None

    def test_splitSummaries_silently_dropped(self):
        """splitSummaries is a nested climbing dict — none of the 5-tuple keys
        match, so it's naturally filtered out."""
        client = Mock()
        client.connectapi.return_value = _RUNNING_FIXTURE
        rows = api.get_sport_stats(client, "running", "2025-10-20", "2025-10-27")
        # No splitSummaries_* columns should leak in
        assert not any(k.startswith("splitSummaries") for k in rows[0])

    def test_sorted_by_date_ascending(self):
        client = Mock()
        client.connectapi.return_value = list(reversed(_RUNNING_FIXTURE))
        rows = api.get_sport_stats(client, "running", "2025-10-20", "2025-10-27")
        assert [r["date"] for r in rows] == ["2025-10-20", "2025-10-27"]

    def test_empty_response(self):
        client = Mock()
        client.connectapi.return_value = None
        assert api.get_sport_stats(client, "running", "2025-10-20", "2025-10-27") == []


class TestGetSportStatsCycling:
    def test_cycling_activity_type_only_differs(self):
        """Only `activityType` changes between sports — metric list is identical
        to running (verbatim Garmin web-UI list). Verified against HAR."""
        client = Mock()
        client.connectapi.return_value = []
        api.get_sport_stats(client, "cycling", "2025-04-16", "2026-04-15")
        p = client.connectapi.call_args[1]["params"]
        assert p["activityType"] == "cycling"
        # Same 35-metric list as running (sport-agnostic, server filters response)
        assert len(p["metric"]) == 35
        assert "avgBikeCadence" in p["metric"]
        assert "avgRunCadence" in p["metric"]  # sent for cycling too


class TestGetSportStatsValidation:
    def test_unknown_sport(self):
        client = Mock()
        with pytest.raises(ValueError, match="Unknown sport"):
            api.get_sport_stats(client, "swimming", "2025-04-16", "2026-04-15")

    def test_unknown_aggregation(self):
        client = Mock()
        with pytest.raises(ValueError, match="Unknown aggregation"):
            api.get_sport_stats(
                client, "running", "2025-04-16", "2026-04-15", aggregation="hourly"
            )

    def test_aggregation_passed_through(self):
        client = Mock()
        client.connectapi.return_value = []
        api.get_sport_stats(
            client, "running", "2025-04-16", "2026-04-15", aggregation="monthly"
        )
        p = client.connectapi.call_args[1]["params"]
        assert p["aggregation"] == "monthly"


# ── Sleep (ranged endpoint, 28-day chunks) ───────────────────────────────────


def _sleep_daily_response(dates: list[str]) -> dict:
    """Synthesize a /sleep-service/stats/sleep/daily response."""
    return {
        "overallStats": {"averageSleepScore": 75},
        "individualStats": [
            {
                "calendarDate": d,
                "values": {
                    "sleepScore": 77,
                    "sleepScoreQuality": "FAIR",
                    "totalSleepTimeInSeconds": 24000,
                    "deepTime": 3600,
                    "lightTime": 12000,
                    "remTime": 7200,
                    "awakeTime": 1200,
                    "sleepNeed": 490,  # MINUTES (not seconds — Garmin quirk)
                    "restingHeartRate": 58,
                    "avgHeartRate": 62.3,
                    "respiration": 16.5,
                    "spO2": 96.7,
                    "bodyBatteryChange": 50,
                    "avgOvernightHrv": 45.0,
                    "hrv7dAverage": 43.0,
                    "hrvStatus": "BALANCED",
                    "localSleepStartTimeInMillis": 1775682605000,
                    "localSleepEndTimeInMillis": 1775711105000,
                },
            }
            for d in dates
        ],
    }


class TestChunkRange:
    def test_range_smaller_than_chunk(self):
        assert api._chunk_range("2026-04-13", "2026-04-15", 28) == [
            ("2026-04-13", "2026-04-15"),
        ]

    def test_range_exactly_chunk_size(self):
        chunks = api._chunk_range("2026-03-19", "2026-04-15", 28)
        assert chunks == [("2026-03-19", "2026-04-15")]
        assert len(chunks) == 1

    def test_365_days_gets_13_chunks(self):
        chunks = api._chunk_range("2025-04-16", "2026-04-15", 28)
        assert len(chunks) == 14  # 365 days / 28 = 13 full + 1 partial
        # Contiguous, no overlap
        for (_, prev_end), (cur_start, _) in zip(chunks, chunks[1:]):
            prev_d = datetime.strptime(prev_end, "%Y-%m-%d").date()
            cur_d = datetime.strptime(cur_start, "%Y-%m-%d").date()
            assert (cur_d - prev_d).days == 1
        assert chunks[0][0] == "2025-04-16"
        assert chunks[-1][1] == "2026-04-15"


class TestGetSleep:
    def test_single_chunk_flatten(self):
        client = Mock()
        client.connectapi.return_value = _sleep_daily_response(
            ["2026-04-13", "2026-04-14", "2026-04-15"]
        )
        rows = api.get_sleep(client, "2026-04-13", "2026-04-15")
        assert len(rows) == 3
        assert [r["date"] for r in rows] == ["2026-04-13", "2026-04-14", "2026-04-15"]
        r = rows[0]
        # Raw Garmin field names, passed through verbatim
        assert r["sleepScore"] == 77
        assert r["sleepScoreQuality"] == "FAIR"
        assert r["totalSleepTimeInSeconds"] == 24000
        assert r["deepTime"] == 3600
        assert r["sleepNeed"] == 490  # minutes (documented quirk)
        assert r["avgOvernightHrv"] == 45.0
        assert r["hrv7dAverage"] == 43.0
        assert r["hrvStatus"] == "BALANCED"
        assert r["restingHeartRate"] == 58
        assert r["spO2"] == 96.7
        # Single chunk → single HTTP call
        assert client.connectapi.call_count == 1
        args, _ = client.connectapi.call_args
        assert args[0] == "/sleep-service/stats/sleep/daily/2026-04-13/2026-04-15"

    def test_365_days_chunks_and_merges(self):
        client = Mock()
        # Every call returns a response for its chunk range
        def _resp(path, **kw):
            # Path: "/sleep-service/stats/sleep/daily/<s>/<e>"
            parts = path.rsplit("/", 2)
            s, e = parts[-2], parts[-1]
            dates = api._daterange(s, e)
            return _sleep_daily_response(dates)

        client.connectapi.side_effect = _resp
        rows = api.get_sleep(client, "2025-04-16", "2026-04-15")
        assert len(rows) == 365  # inclusive — 365 days covered, 14 chunks
        # Deduped + sorted
        assert rows[0]["date"] == "2025-04-16"
        assert rows[-1]["date"] == "2026-04-15"
        assert client.connectapi.call_count == 14

    def test_chunk_failure_is_non_fatal(self):
        client = Mock()
        calls = []
        def _resp(path, **kw):
            calls.append(path)
            if "2026-04-02" in path:
                raise RuntimeError("boom")
            parts = path.rsplit("/", 2)
            dates = api._daterange(parts[-2], parts[-1])
            return _sleep_daily_response(dates)
        client.connectapi.side_effect = _resp
        rows = api.get_sleep(client, "2026-03-01", "2026-04-15")
        # Still got data from other chunks
        assert len(rows) > 0
        # Didn't include failed chunk's dates
        assert not any("2026-04-02" <= r["date"] <= "2026-04-15" for r in rows[:20])

    def test_empty_response(self):
        client = Mock()
        client.connectapi.return_value = None
        assert api.get_sleep(client, "2026-04-13", "2026-04-15") == []

    def test_dedupe_on_overlap(self):
        """Guard: if chunks accidentally overlap (bug or server quirk), dedupe wins."""
        client = Mock()
        client.connectapi.return_value = _sleep_daily_response(
            ["2026-04-13", "2026-04-13", "2026-04-14"]
        )
        rows = api.get_sleep(client, "2026-04-13", "2026-04-14")
        assert len(rows) == 2
        assert [r["date"] for r in rows] == ["2026-04-13", "2026-04-14"]


# ── Heart rate (ranged /usersummary-service/stats/heartRate/) ────────────────


def _hr_daily_response(dates: list[str]) -> list[dict]:
    return [
        {"calendarDate": d, "values": {"restingHR": 57, "wellnessMaxAvgHR": 160, "wellnessMinAvgHR": 55}}
        for d in dates
    ]


def _hr_weekly_response(week_starts: list[str]) -> list[dict]:
    return [
        {"calendarDate": d, "values": {"avgRestingHR": 59, "wellnessMaxAvgHR": 167, "wellnessMinAvgHR": 57}}
        for d in week_starts
    ]


class TestGetHeartRate:
    def test_daily_single_chunk(self):
        client = Mock()
        client.connectapi.return_value = _hr_daily_response(["2026-04-13", "2026-04-14", "2026-04-15"])
        rows = api.get_heart_rate(client, "2026-04-13", "2026-04-15")
        assert len(rows) == 3
        assert rows[0]["date"] == "2026-04-13"
        assert rows[0]["restingHR"] == 57
        assert rows[0]["wellnessMaxAvgHR"] == 160
        # Single chunk → 1 HTTP call
        assert client.connectapi.call_count == 1
        assert client.connectapi.call_args.args[0] == "/usersummary-service/stats/heartRate/daily/2026-04-13/2026-04-15"

    def test_daily_chunked_for_long_range(self):
        client = Mock()
        def _resp(path, **kw):
            parts = path.rsplit("/", 2)
            return _hr_daily_response(api._daterange(parts[-2], parts[-1]))
        client.connectapi.side_effect = _resp
        rows = api.get_heart_rate(client, "2025-04-16", "2026-04-15")
        assert len(rows) == 365
        assert rows[0]["date"] == "2025-04-16"
        assert rows[-1]["date"] == "2026-04-15"
        # 14 chunks for 365 days
        assert client.connectapi.call_count == 14

    def test_weekly_single_call(self):
        client = Mock()
        client.connectapi.return_value = _hr_weekly_response(
            ["2025-10-23", "2025-10-30", "2026-04-09"]
        )
        rows = api.get_heart_rate(client, "2025-04-16", "2026-04-15", aggregation="weekly")
        assert len(rows) == 3
        # Weekly field name differs from daily
        assert rows[0]["avgRestingHR"] == 59
        # 1 HTTP call, end-date based URL with weeks count
        assert client.connectapi.call_count == 1
        path = client.connectapi.call_args.args[0]
        assert path.startswith("/usersummary-service/stats/heartRate/weekly/2026-04-15/")
        # weeks count in path
        assert "/52" in path or "/53" in path

    def test_weekly_caps_at_52(self):
        """Server rejects >52 weeks. We clamp client-side."""
        client = Mock()
        client.connectapi.return_value = []
        api.get_heart_rate(client, "2023-01-01", "2026-04-15", aggregation="weekly")
        path = client.connectapi.call_args.args[0]
        # Must contain /52 not /100+
        assert path.endswith("/52")

    def test_unknown_aggregation(self):
        client = Mock()
        with pytest.raises(ValueError, match="Unknown aggregation"):
            api.get_heart_rate(client, "2026-04-13", "2026-04-15", aggregation="monthly")

    def test_chunk_failure_non_fatal(self):
        client = Mock()
        def _resp(path, **kw):
            if "2026-04-01" in path:
                raise RuntimeError("boom")
            parts = path.rsplit("/", 2)
            return _hr_daily_response(api._daterange(parts[-2], parts[-1]))
        client.connectapi.side_effect = _resp
        rows = api.get_heart_rate(client, "2026-03-01", "2026-04-15")
        assert len(rows) > 0


# ── VO2 max (ranged /maxmet/ endpoint, per-sport) ────────────────────────────


class TestGetVo2Max:
    def _responder(self, running_data, cycling_data):
        """Simulate /maxmet/{agg}/{start}/{end}?sport=X."""
        def _connectapi(path, params=None, **_):
            sport = (params or {}).get("sport")
            if sport == "running":
                return running_data
            if sport == "cycling":
                return cycling_data
            return None
        return _connectapi

    def test_two_calls_per_sport(self):
        client = Mock()
        client.connectapi.side_effect = self._responder([], [])
        api.get_vo2max(client, "2025-04-16", "2026-04-15")
        assert client.connectapi.call_count == 2
        paths = [c.args[0] for c in client.connectapi.call_args_list]
        sports = [c.kwargs["params"]["sport"] for c in client.connectapi.call_args_list]
        assert all("/metrics-service/metrics/maxmet/daily/2025-04-16/2026-04-15" == p for p in paths)
        assert sorted(sports) == ["cycling", "running"]

    def test_aggregation_passed_in_url(self):
        client = Mock()
        client.connectapi.side_effect = self._responder([], [])
        api.get_vo2max(client, "2025-04-16", "2026-04-15", aggregation="monthly")
        assert all("/maxmet/monthly/" in c.args[0] for c in client.connectapi.call_args_list)

    def test_flattens_generic_wrapper(self):
        running = [
            {
                "userId": 138658236,
                "generic": {
                    "calendarDate": "2026-03-29",
                    "vo2MaxValue": 50.0,
                    "vo2MaxPreciseValue": 49.9,
                    "fitnessAge": None,
                    "fitnessAgeDescription": None,
                    "maxMetCategory": 0,
                },
                "cycling": None,
                "heatAltitudeAcclimation": None,
            },
            {
                "userId": 138658236,
                "generic": {
                    "calendarDate": "2026-04-15",
                    "vo2MaxValue": 50.0,
                    "vo2MaxPreciseValue": 50.4,
                    "fitnessAge": 28,
                    "fitnessAgeDescription": "EXCELLENT",
                    "maxMetCategory": 0,
                },
                "cycling": None,
                "heatAltitudeAcclimation": None,
            },
        ]
        client = Mock()
        client.connectapi.side_effect = self._responder(running, [])
        rows = api.get_vo2max(client, "2026-03-23", "2026-04-15", aggregation="weekly")
        assert len(rows) == 2
        assert all(r["sport"] == "running" for r in rows)
        assert rows[0]["date"] == "2026-03-29"
        assert rows[0]["vo2MaxPreciseValue"] == 49.9
        assert rows[1]["vo2MaxPreciseValue"] == 50.4
        assert rows[1]["fitnessAge"] == 28
        assert rows[1]["fitnessAgeDescription"] == "EXCELLENT"

    def test_empty_cycling_tolerated(self):
        """User has no cycling VO2max — response is empty list, should not break."""
        running = [{"generic": {"calendarDate": "2026-04-15", "vo2MaxValue": 50}}]
        client = Mock()
        client.connectapi.side_effect = self._responder(running, [])
        rows = api.get_vo2max(client, "2026-04-15", "2026-04-15")
        assert len(rows) == 1
        assert rows[0]["sport"] == "running"

    def test_merges_both_sports(self):
        running = [{"generic": {"calendarDate": "2026-04-15", "vo2MaxValue": 50.0}}]
        cycling = [{"generic": {"calendarDate": "2026-04-15", "vo2MaxValue": 45.0}}]
        client = Mock()
        client.connectapi.side_effect = self._responder(running, cycling)
        rows = api.get_vo2max(client, "2026-04-15", "2026-04-15")
        assert len(rows) == 2
        sports = {r["sport"]: r for r in rows}
        assert sports["running"]["vo2MaxValue"] == 50.0
        assert sports["cycling"]["vo2MaxValue"] == 45.0

    def test_skips_entries_without_calendar_date(self):
        running = [
            {"generic": {"calendarDate": None, "vo2MaxValue": 50}},
            {"generic": None},
            {"generic": {"calendarDate": "2026-04-15", "vo2MaxValue": 50}},
        ]
        client = Mock()
        client.connectapi.side_effect = self._responder(running, [])
        rows = api.get_vo2max(client, "2026-04-15", "2026-04-15")
        assert len(rows) == 1
        assert rows[0]["date"] == "2026-04-15"

    def test_unknown_aggregation_rejected(self):
        client = Mock()
        with pytest.raises(ValueError, match="Unknown aggregation"):
            api.get_vo2max(client, "2025-04-16", "2026-04-15", aggregation="yearly")

    def test_one_sport_fails_other_succeeds(self):
        """Non-fatal: if running call errors, cycling can still succeed."""
        running_resp = [{"generic": {"calendarDate": "2026-04-15", "vo2MaxValue": 50}}]
        def _connectapi(path, params=None, **_):
            if params["sport"] == "running":
                raise RuntimeError("boom")
            return running_resp  # return for cycling too
        client = Mock()
        client.connectapi.side_effect = _connectapi
        rows = api.get_vo2max(client, "2026-04-15", "2026-04-15")
        assert len(rows) == 1
        assert rows[0]["sport"] == "cycling"


# ── Race predictions (single range call) ─────────────────────────────────────


class TestGetRacePredictions:
    def test_range_sorted(self):
        client = Mock()
        client.get_race_predictions.return_value = [
            {"calendarDate": "2026-04-15", "time5K": 1200, "time10K": 2500, "timeHalfMarathon": 5400, "timeMarathon": 11400},
            {"calendarDate": "2026-04-14", "time5K": 1210, "time10K": 2520, "timeHalfMarathon": 5440, "timeMarathon": 11500},
        ]
        rows = api.get_race_predictions(client, "2026-04-14", "2026-04-15")
        assert len(rows) == 2
        assert [r["date"] for r in rows] == ["2026-04-14", "2026-04-15"]
        assert rows[1]["race_5k_seconds"] == 1200
        assert rows[1]["race_marathon_seconds"] == 11400
        client.get_race_predictions.assert_called_once_with(
            startdate="2026-04-14", enddate="2026-04-15", _type="daily"
        )

    def test_dict_wrapped_to_single_row(self):
        client = Mock()
        client.get_race_predictions.return_value = {
            "calendarDate": "2026-04-15",
            "time5K": 1200,
        }
        rows = api.get_race_predictions(client, "2026-04-15", "2026-04-15")
        assert len(rows) == 1
        assert rows[0]["race_5k_seconds"] == 1200

    def test_empty(self):
        client = Mock()
        client.get_race_predictions.return_value = None
        assert api.get_race_predictions(client, "2026-04-01", "2026-04-15") == []


# ── Default window ───────────────────────────────────────────────────────────


class TestDefaultWindow:
    def test_365_days(self):
        start, end = api.default_window(365)
        from datetime import datetime

        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        assert (e - s).days == 365

    def test_custom_days(self):
        start, end = api.default_window(30)
        from datetime import datetime

        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        assert (e - s).days == 30
