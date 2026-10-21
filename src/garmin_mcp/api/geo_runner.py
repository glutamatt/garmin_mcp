"""Client of the geo-runner service (a Hugging Face Space), shared by every
`geographic` command.

The free Space sleeps after 48 h without calls. While it starts again (1 to 3
min), the Hugging Face proxy answers 502 / 503 / 504, often with an empty body:
geo-runner itself never sends these codes. So a call:

1. wakes the Space up with a light GET, again and again, with growing waits
   (the `Retry-After` header wins when it asks for more), within a budget of
   about 2 minutes;
2. then sends the real POST. Its body (FIT, DuckDB) stays in memory, so a 50x
   on the POST goes back to step 1 and sends the same body again, in the same
   budget.

Seen on the real Space (2026-10-02), asleep: the proxy held the first GET for
9 s, then geo-runner answered 200. The 50x come when the start takes longer.

When the budget runs out, a 503 alone cannot tell "still starting" from "down"
(seen on 17/10: 3 × 100 s of "se réveille" while the Space was broken). The
failure then reads the Space's stage on the Hugging Face API
(`/api/spaces/<id>/runtime`, no auth) and says which one it is (exit 1 both):
- starting (`BUILDING`, `APP_STARTING`…): try again in 60 s;
- down (`RUNTIME_ERROR`, `PAUSED`…, or `RUNNING` and still 50x after 2 min):
  do not try again, tell the developer.
A 429 is `RateLimited` (exit 1), never retried. Any other error answer gives its
status and its message, never an empty message.

The URL comes from `GEO_RUNNER_URL` (local geo-runner in dev), else the
production Space (`GEO_RUNNER_SPACE_ID`, default `DEFAULT_SPACE_ID`).
"""

import os
import time
from email.utils import parsedate_to_datetime

import requests

from garmin_mcp.api.contract import Unavailable, http_failure

DEFAULT_SPACE_ID = "glutamatt/geo-runner"
SPACE_RUNTIME_URL = "https://huggingface.co/api/spaces/{space_id}/runtime"
RUNTIME_TIMEOUT_S = 10

# Stages of a Hugging Face Space (`runtime.stage`).
STARTING_STAGES = frozenset({"BUILDING", "APP_STARTING", "RUNNING_BUILDING", "RUNNING_APP_STARTING", "SLEEPING"})
DOWN_STAGES = frozenset({"RUNTIME_ERROR", "BUILD_ERROR", "CONFIG_ERROR", "NO_APP_FILE", "PAUSED", "STOPPED",
                         "DELETING"})

# A cheap GET of geo-runner (a small JSON, no database work): wakes the Space up.
WAKE_PATH = "/api/narrative-defaults"

# HTTP codes of the Hugging Face proxy while the Space starts.
WAKING_STATUSES = frozenset({502, 503, 504})

WAKE_BUDGET_S = 120
FIRST_WAIT_S = 3
MAX_WAIT_S = 20
WAKE_TIMEOUT_S = 30
# A POST does the real work (a 10-FIT ingest can take a while): its own timeout,
# outside the wake-up budget.
REQUEST_TIMEOUT_S = 120

WAKING_MESSAGE = "geo-runner se réveille (1-3 min), réessaie dans 60 s"
DOWN_MESSAGE = "geo-runner est en panne : ne réessaie pas, préviens l'athlète et Mathieu (dev)"
UNKNOWN_MESSAGE = ("geo-runner ne répond pas (état du Space inconnu) : réessaie une fois dans 60 s ; "
                   "s'il ne répond toujours pas, il est en panne : préviens l'athlète et Mathieu (dev)")

# Replaced in tests, so that they do not really wait.
_sleep = time.sleep
_clock = time.monotonic


def space_id() -> str | None:
    """The Hugging Face Space of geo-runner: `GEO_RUNNER_SPACE_ID`, else the production
    one when `GEO_RUNNER_URL` is not set; None for a local geo-runner."""
    configured = os.environ.get("GEO_RUNNER_SPACE_ID")
    if configured:
        return configured
    return None if os.environ.get("GEO_RUNNER_URL") else DEFAULT_SPACE_ID


def space_url(space: str) -> str:
    """A Space's own domain: `owner/name` → `https://owner-name.hf.space` (Hugging Face's rule)."""
    host = space.replace("/", "-").replace("_", "-").replace(".", "-").lower()
    return f"https://{host}.hf.space"


def base_url() -> str:
    """The geo-runner base URL: `GEO_RUNNER_URL`, else the Space's domain."""
    return (os.environ.get("GEO_RUNNER_URL") or space_url(space_id() or DEFAULT_SPACE_ID)).rstrip("/")


def post(path: str, what: str, **request) -> requests.Response:
    """POST `path` on geo-runner once it is awake; its 2xx response.

    `what` names the call in failure messages ("geo-runner ingest 400: …").
    `request` holds the `requests.post` arguments (`files`, `data`, `params`):
    bytes only, so that a retry can send them again.
    """
    tries = _Tries()
    while True:
        _wake_up(tries)
        try:
            resp = requests.post(f"{base_url()}{path}", timeout=REQUEST_TIMEOUT_S, **request)
        except requests.RequestException as e:
            raise Unavailable(f"{what} request failed: {e}")
        if resp.ok:
            return resp
        if resp.status_code not in WAKING_STATUSES:
            raise http_failure(resp.status_code, f"{what} {resp.status_code}: {_detail(resp)}")
        # The Space went back to sleep or restarted between the GET and the POST.
        tries.wait(f"HTTP {resp.status_code}", _retry_after_s(resp))


def _wake_up(tries: "_Tries") -> None:
    """GET the wake-up path until geo-runner itself answers."""
    while True:
        try:
            resp = requests.get(f"{base_url()}{WAKE_PATH}", timeout=WAKE_TIMEOUT_S)
        except requests.RequestException as e:
            # The proxy can drop the connection or hang while the Space starts.
            tries.wait(type(e).__name__, 0)
            continue
        if resp.ok and _is_json(resp):
            return
        if resp.ok or resp.status_code in WAKING_STATUSES:
            # A 2xx that is not geo-runner's JSON is a proxy page: still starting.
            tries.wait(f"HTTP {resp.status_code}", _retry_after_s(resp))
            continue
        raise http_failure(
            resp.status_code, f"geo-runner wake-up {resp.status_code}: {_detail(resp)}"
        )


class _Tries:
    """The wake-up budget of one call: growing waits, `Retry-After` when it asks for more."""

    def __init__(self):
        self.start = _clock()
        self.next_wait = FIRST_WAIT_S

    def wait(self, last: str, retry_after: float) -> None:
        """Sleep before the next try, or fail when the wait goes past the budget."""
        wait = max(self.next_wait, retry_after)
        elapsed = _clock() - self.start
        if elapsed + wait > WAKE_BUDGET_S:
            raise Unavailable(f"{_out_of_budget_message()} (dernière réponse après {elapsed:.0f} s : {last})")
        _sleep(wait)
        self.next_wait = min(self.next_wait * 2, MAX_WAIT_S)


def _out_of_budget_message() -> str:
    """Why geo-runner still does not answer after the budget: starting, or down."""
    stage = _space_stage()
    if stage in STARTING_STAGES:
        return f"{WAKING_MESSAGE} (Space : {stage})"
    if stage in DOWN_STAGES:
        return f"{DOWN_MESSAGE} (Space : {stage})"
    if stage == "RUNNING":
        # The Space says it runs, the proxy still answers 50x after 2 min: geo-runner is broken.
        return f"{DOWN_MESSAGE} (Space : RUNNING, mais pas de réponse depuis {WAKE_BUDGET_S} s)"
    return UNKNOWN_MESSAGE if stage is None else f"{UNKNOWN_MESSAGE} (Space : {stage})"


def _space_stage() -> str | None:
    """The Space's stage from the Hugging Face API, or None (local geo-runner, API down)."""
    space = space_id()
    if not space:
        return None
    try:
        resp = requests.get(SPACE_RUNTIME_URL.format(space_id=space), timeout=RUNTIME_TIMEOUT_S)
        stage = resp.json().get("stage") if resp.ok else None
    except (requests.RequestException, ValueError, AttributeError):
        return None
    return stage if isinstance(stage, str) else None


def _retry_after_s(resp) -> float:
    """The `Retry-After` header in seconds (a number or an HTTP date), 0 if none."""
    value = (resp.headers.get("Retry-After") or "").strip() if resp is not None else ""
    if not value:
        return 0
    try:
        return max(float(value), 0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return 0
    return max(when.timestamp() - time.time(), 0)


def _is_json(resp: requests.Response) -> bool:
    return resp.headers.get("Content-Type", "").startswith("application/json")


def _detail(resp: requests.Response) -> str:
    """The message of an error answer: geo-runner's `{"error": …}`, else the
    start of the body, else the HTTP reason. Never empty."""
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("error"):
        return str(body["error"])
    text = (resp.text or "").strip()
    if text:
        return text[:300]
    return f"{resp.reason or 'no reason'} (empty body)"
