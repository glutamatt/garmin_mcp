"""The geo-runner client (`api/geo_runner.py`) against a fake geo-runner over real HTTP.

- a sleeping Space (502/503/504, empty body, proxy page) is woken up and tried
  again with growing waits; `Retry-After` wins when it asks for more;
- a 50x on the POST wakes the Space up again and sends the same body again;
- when the ~2 min budget runs out: "geo-runner se réveille…", exit 1;
- 429 → `RateLimited`, exit 1, no retry; other errors keep their message, never empty;
- `--output` names the data file of `geographic activity`, `geographic history
  query` and `activities download`; the answer goes to stdout.

The fake server answers from a script, in order. The client's clock and sleep
are fake: no test really waits.
"""

import email.utils
import io
import json
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

import pytest

from garmin_mcp.api import geo_history, geo_runner
from garmin_mcp.api.activities import download_fit
from garmin_mcp.api.contract import RateLimited, Unavailable
from garmin_mcp.cli import execute

AWAKE = (200, {"Content-Type": "application/json"}, b'{"min_duration_s": 39}')
WAKING = (503, {}, b"")
TSV = "# Run 2026-01-01 — 5.00 km\nt_start\tname\n0:00:00\tparc\n0:10:00\true\n"


def analyzed(text: str = TSV):
    return (200, {"Content-Type": "text/tab-separated-values; charset=utf-8"}, text.encode())


class FakeGeoRunner:
    """A geo-runner on localhost: answers `script` in order, records each request."""

    def __init__(self):
        self.script: list[tuple[int, dict, bytes]] = []
        self.requests: list[tuple[str, str, bytes]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self):
                length = int(self.headers.get("Content-Length") or 0)
                fake.requests.append((self.command, self.path, self.rfile.read(length)))
                status, headers, body = fake.script.pop(0)
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _answer

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, args=(0.01,), daemon=True).start()

    def methods(self) -> list[str]:
        return [f"{method} {path.split('?')[0]}" for method, path, _ in self.requests]

    def posts(self) -> list[bytes]:
        """The POST bodies, without their multipart boundary (new at each send)."""
        bodies = [body for method, _, body in self.requests if method == "POST"]
        return [body.replace(body.split(b"\r\n", 1)[0], b"--BOUNDARY") for body in bodies]


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.waits: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time(monkeypatch):
    fake = FakeTime()
    monkeypatch.setattr(geo_runner, "_clock", fake.clock)
    monkeypatch.setattr(geo_runner, "_sleep", fake.sleep)
    return fake


@pytest.fixture
def geo(monkeypatch, fake_time):
    server = FakeGeoRunner()
    monkeypatch.setenv("GEO_RUNNER_URL", server.url + "/")
    yield server
    server.server.shutdown()
    server.server.server_close()


def _post(**request):
    return geo_runner.post("/api/analyze", "geo-runner analyze", **request)


# ── URL ──────────────────────────────────────────────────────────────────────


class TestBaseUrl:
    def test_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("GEO_RUNNER_URL", "http://localhost:7870/")
        assert geo_runner.base_url() == "http://localhost:7870"

    def test_production_space_by_default(self, monkeypatch):
        monkeypatch.delenv("GEO_RUNNER_URL", raising=False)
        assert geo_runner.base_url() == "https://glutamatt-geo-runner.hf.space"


# ── Wake-up and retries ──────────────────────────────────────────────────────


class TestWakeUp:
    def test_awake_space_is_one_get_then_the_post(self, geo, fake_time):
        geo.script = [AWAKE, analyzed()]
        assert _post(files={"fit": ("a.fit", b"FIT", "application/octet-stream")}).text == TSV
        assert geo.methods() == ["GET /api/narrative-defaults", "POST /api/analyze"]
        assert fake_time.waits == []

    @pytest.mark.parametrize("status", [502, 503, 504])
    def test_proxy_codes_wait_more_and_more(self, geo, fake_time, status):
        geo.script = [(status, {}, b""), (status, {}, b""), (status, {}, b""), AWAKE, analyzed()]
        assert _post(files={"fit": ("a.fit", b"FIT", "application/octet-stream")}).ok
        assert fake_time.waits == [3, 6, 12]
        assert geo.methods()[-1] == "POST /api/analyze"
        assert len(geo.posts()) == 1

    def test_a_2xx_that_is_not_geo_runner_json_is_a_proxy_page(self, geo, fake_time):
        page = (200, {"Content-Type": "text/html"}, b"<html>Space is starting</html>")
        geo.script = [page, AWAKE, analyzed()]
        assert _post().ok
        assert fake_time.waits == [3]

    def test_retry_after_in_seconds_wins_when_longer(self, geo, fake_time):
        geo.script = [(503, {"Retry-After": "25"}, b""), (503, {"Retry-After": "1"}, b""), AWAKE, analyzed()]
        assert _post().ok
        assert fake_time.waits == [25, 6]

    def test_retry_after_as_an_http_date(self, geo, fake_time):
        when = email.utils.formatdate(time.time() + 40, usegmt=True)
        geo.script = [(503, {"Retry-After": when}, b""), AWAKE, analyzed()]
        assert _post().ok
        assert 35 <= fake_time.waits[0] <= 40

    def test_a_50x_on_the_post_wakes_up_again_and_sends_the_same_body(self, geo, fake_time):
        geo.script = [AWAKE, WAKING, WAKING, AWAKE, analyzed()]
        fit = bytes(range(256)) * 40
        assert _post(files={"fit": ("a.fit", fit, "application/octet-stream")}).ok
        assert geo.methods() == [
            "GET /api/narrative-defaults", "POST /api/analyze",
            "GET /api/narrative-defaults", "GET /api/narrative-defaults", "POST /api/analyze",
        ]
        first, second = geo.posts()
        assert first == second and fit in first
        assert fake_time.waits == [3, 6]

    def test_budget_out_says_the_space_is_waking_up(self, geo, fake_time):
        geo.script = [WAKING] * 50
        with pytest.raises(Unavailable) as failure:
            _post()
        assert str(failure.value).startswith("geo-runner se réveille (1-3 min), réessaie dans 60 s")
        assert "HTTP 503" in str(failure.value)
        assert not isinstance(failure.value, RateLimited)
        assert failure.value.exit_code == 1
        assert sum(fake_time.waits) <= geo_runner.WAKE_BUDGET_S
        assert fake_time.waits[:5] == [3, 6, 12, 20, 20]
        assert geo.posts() == []

    def test_retry_after_past_the_budget_gives_up_at_once(self, geo, fake_time):
        geo.script = [(503, {"Retry-After": "600"}, b"")]
        with pytest.raises(Unavailable, match="se réveille"):
            _post()
        assert fake_time.waits == []

    def test_the_budget_counts_the_post_retries_too(self, geo, fake_time):
        geo.script = [AWAKE, WAKING] * 30
        with pytest.raises(Unavailable, match="se réveille"):
            _post()
        assert sum(fake_time.waits) <= geo_runner.WAKE_BUDGET_S

    def test_no_server_is_retried_then_waking_message(self, monkeypatch, fake_time):
        monkeypatch.setenv("GEO_RUNNER_URL", "http://127.0.0.1:9")
        with pytest.raises(Unavailable, match="se réveille.*ConnectionError"):
            _post()
        assert fake_time.waits[:3] == [3, 6, 12]


# ── Error answers ────────────────────────────────────────────────────────────


class TestErrorAnswers:
    def test_429_on_the_post_is_rate_limited_and_not_retried(self, geo, fake_time):
        geo.script = [AWAKE, (429, {}, b"")]
        with pytest.raises(RateLimited, match="geo-runner analyze 429") as failure:
            _post()
        assert failure.value.exit_code == 1
        assert len(geo.posts()) == 1
        assert fake_time.waits == []

    def test_429_on_the_wake_up_is_rate_limited(self, geo, fake_time):
        geo.script = [(429, {}, b"slow down")]
        with pytest.raises(RateLimited, match="geo-runner wake-up 429: slow down"):
            _post()

    def test_geo_runner_error_json_is_the_message(self, geo, fake_time):
        geo.script = [AWAKE, (400, {"Content-Type": "application/json"}, b'{"error": "not a FIT file"}')]
        with pytest.raises(Unavailable, match="^geo-runner analyze 400: not a FIT file$"):
            _post()
        assert len(geo.posts()) == 1

    def test_an_empty_body_still_gives_a_message(self, geo, fake_time):
        geo.script = [AWAKE, (500, {}, b"")]
        with pytest.raises(Unavailable, match=r"^geo-runner analyze 500: Internal Server Error \(empty body\)$"):
            _post()

    def test_a_text_body_is_cut(self, geo, fake_time):
        geo.script = [AWAKE, (500, {}, b"x" * 1000)]
        with pytest.raises(Unavailable) as failure:
            _post()
        assert str(failure.value) == "geo-runner analyze 500: " + "x" * 300


# ── FIT download (one copy, used by every geographic command) ────────────────


def _zip(names: list[str], data: bytes = b"FIT DATA") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name in names:
            zf.writestr(name, data)
    return buffer.getvalue()


class TestDownloadFit:
    def test_the_fit_inside_the_zip(self):
        client = Mock()
        client.download_activity.return_value = _zip(["notes.txt", "1_ACTIVITY.fit"])
        assert download_fit(client, 1) == b"FIT DATA"

    def test_not_a_zip_is_unavailable(self):
        client = Mock()
        client.download_activity.return_value = b"<html>"
        with pytest.raises(Unavailable, match="not a valid zip"):
            download_fit(client, 1)

    def test_a_garmin_failure_is_left_to_the_contract(self):
        """No wrapping: `as_garmin_error` types it (429 → RateLimited, 404 → NotFound…)."""
        client = Mock()
        client.download_activity.side_effect = KeyError("boom")
        with pytest.raises(KeyError):
            download_fit(client, 1)


# ── CLI: --output names the data file ────────────────────────────────────────


def _client() -> Mock:
    client = Mock()
    client.download_activity.return_value = _zip(["1_ACTIVITY.fit"])
    client.garth.username = "runner@example.com"
    return client


def _run(command: str, client: Mock, tmp_dir: str) -> dict:
    with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
        return execute(command, "fake_token", tmp_dir=tmp_dir)


@pytest.fixture
def sandbox(tmp_path):
    path = tmp_path / "session"
    path.mkdir()
    return path


class TestGeographicActivityCli:
    def test_default_file_name(self, geo, sandbox):
        geo.script = [AWAKE, analyzed()]
        result = _run("geographic activity 1", _client(), str(sandbox))
        assert result["exit_code"] == 0, result["stderr"]
        answer = json.loads(result["stdout"])
        assert answer["path"] == str(sandbox / "geographic_1.tsv")
        assert answer["rows"] == 2
        assert (sandbox / "geographic_1.tsv").read_text() == TSV

    def test_output_names_the_tsv_and_the_answer_goes_to_stdout(self, geo, sandbox):
        geo.script = [AWAKE, analyzed()]
        result = _run("geographic activity 1 --output geo9.tsv", _client(), str(sandbox))
        assert result["exit_code"] == 0, result["stderr"]
        assert json.loads(result["stdout"])["path"] == str(sandbox / "geo9.tsv")
        assert (sandbox / "geo9.tsv").read_text() == TSV
        assert not (sandbox / "geographic_1.tsv").exists()

    def test_waking_space_is_exit_1_with_the_message_and_no_file(self, geo, sandbox):
        geo.script = [WAKING] * 50
        result = _run("geographic activity 1 --output geo9.tsv", _client(), str(sandbox))
        assert result["exit_code"] == 1
        assert result["stdout"] == ""
        assert "geo-runner se réveille (1-3 min), réessaie dans 60 s" in result["stderr"]
        assert list(sandbox.iterdir()) == []

    def test_rate_limit_is_exit_1(self, geo, sandbox):
        geo.script = [AWAKE, (429, {}, b"")]
        result = _run("geographic activity 1", _client(), str(sandbox))
        assert result["exit_code"] == 1
        assert "geo-runner analyze 429" in result["stderr"]


class TestGeographicHistoryCli:
    HEATMAP = {
        "data_as_of": "2026-01-02",
        "results": [
            {"count": 3, "last_day": "2026-01-02", "entity_type": "polygon",
             "relation": "within", "id": "w1", "display": "Parc A"},
            {"count": 1, "last_day": "2026-01-01", "entity_type": "line",
             "relation": "along", "id": "w2", "display": "(chemin piéton)"},
        ],
    }

    @pytest.fixture(autouse=True)
    def user_db_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(geo_history, "USER_DB_DIR", str(tmp_path / "geo-history"))

    def _heatmap(self):
        return (200, {"Content-Type": "application/json"}, json.dumps(self.HEATMAP).encode())

    def test_query_default_file_name_encodes_the_filters(self, geo, sandbox):
        geo.script = [AWAKE, self._heatmap()]
        result = _run("geographic history query heatmap --since 2026-01-01", _client(), str(sandbox))
        assert result["exit_code"] == 0, result["stderr"]
        name = "geographic_history_heatmap_from2026-01-01.tsv"
        assert json.loads(result["stdout"])["path"] == str(sandbox / name)
        assert (sandbox / name).exists()

    def test_query_output_names_the_tsv(self, geo, sandbox):
        geo.script = [AWAKE, self._heatmap()]
        result = _run("geographic history query heatmap --output places.tsv", _client(), str(sandbox))
        assert result["exit_code"] == 0, result["stderr"]
        answer = json.loads(result["stdout"])
        assert answer["path"] == str(sandbox / "places.tsv")
        assert answer["rows"] == 1  # the anonymous `(chemin piéton)` is dropped
        assert "Parc A" in (sandbox / "places.tsv").read_text()
        assert [p.name for p in sandbox.iterdir()] == ["places.tsv"]

    def test_update_sends_the_same_fits_again_after_a_50x(self, geo, sandbox):
        client = _client()
        client.get_activities_by_date.return_value = [
            {"activityId": 1, "startTimeLocal": "2026-01-01 08:00:00",
             "activityType": {"typeKey": "running"}, "distance": 5000, "duration": 1800},
        ]
        boundary = "b0undary"
        ingest = (
            200,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"stats\"\r\n\r\n"
                '{"runs_added": 1, "runs_skipped": 0, "visits_added": 4, "errors": []}\r\n'
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"user_db\"\r\n\r\n"
                "DB\r\n"
                f"--{boundary}--\r\n"
            ).encode(),
        )
        geo.script = [AWAKE, (502, {}, b""), AWAKE, ingest]
        result = _run("geographic history update", client, str(sandbox))
        assert result["exit_code"] == 0, result["stderr"]
        assert json.loads(result["stdout"])["runs_added"] == 1
        first, second = geo.posts()
        assert first == second and b"FIT DATA" in first
        client.download_activity.assert_called_once()


class TestActivitiesDownloadCli:
    def test_output_names_the_csv(self, sandbox):
        fit = Mock()
        fit.get_messages.return_value = []
        with patch("fitparse.FitFile", return_value=fit):
            result = _run("activities download 1 --output run.csv", _client(), str(sandbox))
        assert result["exit_code"] == 0, result["stderr"]
        assert json.loads(result["stdout"])["path"] == str(sandbox / "run.csv")
        assert [p.name for p in sandbox.iterdir()] == ["run.csv"]
