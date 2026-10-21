"""Calendar API: units, ids, the days asked for (shapes of real Garmin answers, made-up values)."""

from unittest.mock import Mock

import pytest

from garmin_mcp.api import calendar as api
from garmin_mcp.cli import execute

ACTIVITY = {
    "id": 101, "itemType": "activity", "activityTypeId": 1, "title": "Morning Run", "date": "2026-04-08",
    "duration": 2041275, "distance": 478041, "calories": 1365, "averageHR": 140.0,
    "startTimestampLocal": "2026-04-08T00:45:49.0", "totalAscent": 2.0,
}
WORKOUT = {"id": 202, "itemType": "workout", "title": "Easy 30", "date": "2026-04-09",
           "sportTypeKey": "running", "workoutId": 303}
EVENT = {
    "id": None, "itemType": "event", "activityTypeId": 1, "title": "Half", "date": "2026-04-12",
    "url": "https://example.org/half", "location": "Somewhere",
    "eventTimeLocal": {"startTimeHhMm": "09:00", "timeZoneId": "Europe/Paris"},
    "completionTarget": {"value": 21.1, "unit": "kilometer", "unitType": "distance"},
    "shareableEventUuid": "u-1",
}


@pytest.fixture
def client():
    c = Mock()
    c.get_calendar_items_for_range.return_value = [EVENT, WORKOUT, ACTIVITY]
    return c


class TestCalendarItems:
    def test_activity_units_and_id(self, client):
        [activity] = [i for i in api.get_month(client, 2026, 4)["items"] if i["type"] == "activity"]
        assert activity == {
            "date": "2026-04-08", "type": "activity", "name": "Morning Run", "activity_id": 101,
            "distance_m": 4780, "duration_s": 2041,
        }

    def test_workout_has_its_schedule_and_workout_ids(self, client):
        [workout] = [i for i in api.get_month(client, 2026, 4)["items"] if i["type"] == "workout"]
        assert workout == {"date": "2026-04-09", "type": "workout", "name": "Easy 30", "sport": "running",
                           "schedule_id": 202, "workout_id": 303}

    def test_race(self, client):
        [race] = [i for i in api.get_month(client, 2026, 4)["items"] if i["type"] == "event"]
        assert race == {"date": "2026-04-12", "type": "event", "name": "Half", "distance_m": 21100,
                        "start_time": "2026-04-12T09:00:00", "location": "Somewhere"}

    def test_month_asks_for_its_own_days_only_and_sorts_by_date(self, client):
        out = api.get_month(client, 2026, 2)
        client.get_calendar_items_for_range.assert_called_once_with("2026-02-01", "2026-02-28")
        assert [i["date"] for i in out["items"]] == ["2026-04-08", "2026-04-09", "2026-04-12"]
        assert out["count"] == 3

    @pytest.mark.parametrize("command", ["calendar month 2026 13", "calendar upcoming --days -1"])
    def test_invalid_input_is_refused_before_garmin(self, command):
        result = execute(command, "fake-token")
        assert result["exit_code"] == 2

    def test_upcoming_from_today(self, client):
        out = api.get_upcoming(client, "2026-04-08", 7)
        client.get_calendar_items_for_range.assert_called_once_with("2026-04-08", "2026-04-15")
        assert (out["from"], out["to"], out["count"]) == ("2026-04-08", "2026-04-15", 3)

    def test_empty_is_count_zero(self, client):
        client.get_calendar_items_for_range.return_value = []
        assert api.get_upcoming(client, "2026-04-08", 7)["items"] == []


class TestEvents:
    def test_race_with_goal_and_activity(self):
        c = Mock()
        c.connectapi.return_value = [{
            "id": 9, "eventName": "Half", "date": "2026-04-12", "eventType": "running",
            "completionTarget": {"value": 21100.0, "unit": "meter", "unitType": "distance"},
            "eventTimeLocal": {"startTimeHhMm": "09:30", "timeZoneId": "Europe/Paris"},
            "location": "Somewhere", "url": "https://example.org/half", "workoutId": None,
            "eventCustomization": {"customGoal": {"value": 6300.0, "unit": "second", "unitType": "time"},
                                   "isPrimaryEvent": False, "associatedWithActivityId": 555},
        }]
        out = api.get_events(c, "2026-04-01", "2026-04-30", 20)
        assert out["count"] == 1
        assert out["events"][0] == {
            "date": "2026-04-12", "name": "Half", "sport": "running", "activity_id": 555, "event_id": 9,
            "distance_m": 21100, "start_time": "2026-04-12T09:30:00", "location": "Somewhere",
            "goal_time_s": 6300, "primary_event": False, "url": "https://example.org/half",
        }
        assert c.connectapi.call_args.kwargs["params"]["limit"] == 20

    def test_no_race_is_count_zero(self):
        c = Mock()
        c.connectapi.return_value = []
        assert api.get_events(c, "2026-04-01", "2026-04-30") == {
            "from": "2026-04-01", "to": "2026-04-30", "count": 0, "events": []}
