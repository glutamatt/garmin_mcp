"""Fixtures for functional tests against real Garmin Connect accounts.

Setup: create .env in garmin_mcp/ root with:

    GARMIN_EMAIL_READONLY=readonly@example.com
    GARMIN_PASSWORD_READONLY=...
    GARMIN_EMAIL_DEV=dev@example.com
    GARMIN_PASSWORD_DEV=...

Or provide pre-authenticated tokens directly:

    GARMIN_TOKEN_READONLY=<base64 garth token>
    GARMIN_TOKEN_DEV=<base64 garth token>

Run:
    cd mcp-servers/garmin_mcp
    .venv/bin/python -m pytest tests/functional/ -v
"""

import os

import pytest
from click.testing import CliRunner
from dotenv import load_dotenv

from garmin_mcp.cli import garmin

# Load .env — try garmin_mcp root, then project root
_garmin_mcp_root = os.path.join(os.path.dirname(__file__), "..", "..")
_project_root = os.path.join(_garmin_mcp_root, "..", "..")
load_dotenv(os.path.join(_garmin_mcp_root, ".env"))
load_dotenv(os.path.join(_project_root, ".env"))  # fallback


def _authenticate(email: str, password: str) -> str:
    """Authenticate with Garmin Connect and return base64 token.

    Caches token in memory for the session.
    """
    from garminconnect import Garmin

    client = Garmin(email=email, password=password, is_cn=False)
    client.login()
    return client.garth.dumps()


# Token cache — login once per pytest session
_token_cache: dict[str, str] = {}


def _get_token(prefix: str) -> str:
    """Get token from env (direct or via credentials). Caches per session."""
    if prefix in _token_cache:
        return _token_cache[prefix]

    # Try direct token first
    token = os.environ.get(f"GARMIN_TOKEN_{prefix}")
    if token:
        _token_cache[prefix] = token
        return token

    # Try credentials
    email = os.environ.get(f"GARMIN_EMAIL_{prefix}")
    password = os.environ.get(f"GARMIN_PASSWORD_{prefix}")
    if email and password:
        token = _authenticate(email, password)
        _token_cache[prefix] = token
        return token

    return ""


@pytest.fixture(scope="session")
def readonly_token():
    """Base64 garth token for read-only account."""
    token = _get_token("READONLY")
    if not token:
        pytest.skip(
            "Set GARMIN_EMAIL_READONLY + GARMIN_PASSWORD_READONLY "
            "(or GARMIN_TOKEN_READONLY) in .env"
        )
    return token


@pytest.fixture(scope="session")
def dev_token():
    """Base64 garth token for dev/write account."""
    token = _get_token("DEV")
    if not token:
        pytest.skip(
            "Set GARMIN_EMAIL_DEV + GARMIN_PASSWORD_DEV "
            "(or GARMIN_TOKEN_DEV) in .env"
        )
    return token


@pytest.fixture
def cli():
    """Click CliRunner with stderr separation."""
    import inspect
    kwargs = {}
    if "mix_stderr" in inspect.signature(CliRunner).parameters:
        kwargs["mix_stderr"] = False
    return CliRunner(**kwargs)


def invoke(cli_runner, token, *args):
    """Helper: invoke garmin CLI with token + args, return result."""
    full_args = ["--token", token] + list(args)
    return cli_runner.invoke(garmin, full_args, catch_exceptions=False)


def invoke_json(cli_runner, token, *args):
    """Helper: invoke and parse JSON output. Asserts exit_code == 0."""
    import json

    result = invoke(cli_runner, token, *args)
    assert result.exit_code == 0, (
        f"CLI failed (exit {result.exit_code}): {result.output}\n"
        f"{getattr(result, 'stderr', '')}"
    )
    return json.loads(result.output)
