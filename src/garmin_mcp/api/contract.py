"""
Output contract of the api layer: data, unavailable, failure.

Every api function answers in one of three ways:

- **Data**, maybe empty. A list answer with no item is a normal answer:
  `{"count": 0, "<items>": []}`. Empty is never an error.
- **Unavailable**: a one-object answer (a day, a section of the snapshot) that
  Garmin cannot give. `unavailable(reason)` →
  `{"available": False, "reason": "no_data" | "not_supported_by_device" | "error: <message>"}`.
  `not_supported_by_device` comes from the device capabilities (`api/capabilities.py`).
- **Failure**: one of the exceptions below. The CLI prints the message on
  stderr and exits with `exit_code` (1, or 2 for invalid input).

`as_garmin_error` turns any other exception (SDK, HTTP, bug) into one of them,
so a caller never has to know the SDK's exception classes.
"""

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from requests import RequestException

from garmin_mcp.client_factory import GarminTokenError

NO_DATA = "no_data"
NOT_SUPPORTED_BY_DEVICE = "not_supported_by_device"


# ── Failures ─────────────────────────────────────────────────────────────────


class GarminError(Exception):
    """The command could not do what was asked."""

    exit_code = 1


class InvalidInput(GarminError, ValueError):
    """The request itself is wrong (format, date window, option value)."""

    exit_code = 2


class NotFound(GarminError):
    """The object asked for does not exist (activity, workout, schedule…)."""


class Unavailable(GarminError):
    """Garmin (or geo-runner) did not answer: network, server error, unusable answer."""


class RateLimited(Unavailable):
    """Too many requests (HTTP 429): the same call can work again in a few minutes."""


class AuthError(GarminError):
    """The Garmin login is not valid any more: every call will fail the same way."""


class GarminWriteError(GarminError):
    """Garmin did not apply a change (create, update, delete, schedule…)."""


def as_garmin_error(exc: BaseException) -> GarminError:
    """The typed failure for an exception raised while answering a command."""
    if isinstance(exc, GarminError):
        return exc
    if isinstance(exc, GarminTokenError):
        return AuthError(str(exc))
    status = _http_status(exc)
    if isinstance(exc, GarminConnectAuthenticationError) or status == 401:
        return AuthError(f"Garmin login refused: {exc}")
    if isinstance(exc, GarminConnectTooManyRequestsError) or status == 429:
        return RateLimited(f"Garmin rate limit (HTTP 429), retry in a few minutes: {exc}")
    if status == 404:
        return NotFound(f"Garmin has no such object (HTTP 404): {exc}")
    if isinstance(exc, (GarminConnectConnectionError, RequestException)):
        return Unavailable(f"Garmin did not answer: {exc}")
    # Not a Garmin failure: most likely a bug. The type name says which one.
    return GarminError(f"{type(exc).__name__}: {exc}")


def http_failure(status: int, message: str) -> Unavailable:
    """The failure for an HTTP error answer of a service we call ourselves (geo-runner)."""
    return (RateLimited if status == 429 else Unavailable)(message)


def _http_status(exc: BaseException) -> int | None:
    """HTTP status of the response behind `exc`, looked up along its chain of causes.

    The SDK wraps garth's `GarthHTTPError` (status in `.error.response`), which
    wraps requests' `HTTPError` (status in `.response`).
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        for holder in (exc, getattr(exc, "error", None)):
            status = getattr(getattr(holder, "response", None), "status_code", None)
            if isinstance(status, int):
                return status
        exc = exc.__cause__ or exc.__context__
    return None


# ── Unavailable ──────────────────────────────────────────────────────────────


def unavailable(reason: str, **context) -> dict:
    """A one-object answer Garmin cannot give, and why."""
    return {**context, "available": False, "reason": reason}


def error_reason(error: GarminError) -> str:
    """The `reason` of a section whose call failed."""
    return f"error: {error}"


def is_unavailable(data) -> bool:
    return isinstance(data, dict) and data.get("available") is False


def has_data(curated: dict | None) -> bool:
    """True when a curated object holds more than its date."""
    return bool(curated) and any(key != "date" for key in curated)


def day_answer(date: str, curated: dict | None) -> dict:
    """A one-day answer: the curated data, or `no_data` when it holds nothing but a date."""
    return curated if has_data(curated) else unavailable(NO_DATA, date=date)
