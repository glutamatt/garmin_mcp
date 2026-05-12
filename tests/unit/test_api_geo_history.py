"""Unit tests for the geo_history orchestrator — covers pure helpers.

The Garmin client + geo-runner HTTP calls live in :func:`update`/:func:`query`
and are tested separately at the integration level (need a running stack).
"""

import os
import tempfile

import duckdb
import pytest

from garmin_mcp.api import geo_history


# ── User-id sanitation / path resolution ────────────────────────────────────


def test_sanitize_user_id_matches_token_store_convention():
    # Same shape as the frontend's `sanitizeFileName` in token-store.ts.
    assert (
        geo_history.sanitize_user_id("garmin:fatal974@hotmail.com")
        == "garmin__fatal974__hotmail.com"
    )


def test_sanitize_user_id_handles_already_sanitized():
    # Idempotent on already-clean ids.
    assert geo_history.sanitize_user_id("garmin__foo") == "garmin__foo"


def test_user_db_path_lands_under_geo_history_dir():
    p = geo_history.user_db_path("garmin:foo@bar.com")
    assert p == "/tmp/neural-runner/geo-history/garmin__foo__bar.com.duckdb"


# ── Local DB introspection ──────────────────────────────────────────────────


def test_latest_day_returns_none_when_db_missing(tmp_path):
    assert geo_history.latest_day_in_db(str(tmp_path / "nope.duckdb")) is None


def test_latest_day_returns_none_on_empty_db(tmp_path):
    p = str(tmp_path / "empty.duckdb")
    # Create empty DB with no schema (same as _ensure_user_db).
    duckdb.connect(p).close()
    assert geo_history.latest_day_in_db(p) is None


def test_latest_day_returns_max_day(tmp_path):
    p = str(tmp_path / "with_data.duckdb")
    con = duckdb.connect(p)
    con.execute(
        """
        CREATE TABLE runs (
            source TEXT, source_activity_id TEXT, day DATE,
            sport TEXT, distance_m INT, duration_s INT,
            PRIMARY KEY (source, source_activity_id)
        )
        """
    )
    con.execute(
        "INSERT INTO runs VALUES "
        "('garmin', 'a1', DATE '2026-03-10', 'running', 5000, 1800), "
        "('garmin', 'a2', DATE '2026-04-15', 'running', 8000, 2400), "
        "('garmin', 'a3', DATE '2026-02-01', 'running', 6000, 2000)"
    )
    con.close()
    assert geo_history.latest_day_in_db(p) == "2026-04-15"


def test_ensure_user_db_creates_missing_file(tmp_path):
    p = str(tmp_path / "nested" / "fresh.duckdb")
    assert not os.path.exists(p)
    geo_history._ensure_user_db(p)
    assert os.path.exists(p)
    # And the resulting file is openable as a DuckDB.
    con = duckdb.connect(p, read_only=True)
    con.close()


def test_ensure_user_db_is_noop_when_present(tmp_path):
    p = str(tmp_path / "exists.duckdb")
    duckdb.connect(p).close()
    before_mtime = os.path.getmtime(p)
    geo_history._ensure_user_db(p)
    # Mtime unchanged — we didn't touch the file.
    assert os.path.getmtime(p) == before_mtime


# ── Multipart decoder ───────────────────────────────────────────────────────


def _build_multipart(boundary: str, parts: list[tuple[str, str, bytes]]) -> bytes:
    """Mirror of the Rust ``build_multipart_body`` in server.rs."""
    buf = bytearray()
    for name, ct, body in parts:
        buf += b"--" + boundary.encode("ascii") + b"\r\n"
        buf += f'Content-Disposition: form-data; name="{name}"\r\n'.encode("ascii")
        buf += f"Content-Type: {ct}\r\n\r\n".encode("ascii")
        buf += body
        buf += b"\r\n"
    buf += b"--" + boundary.encode("ascii") + b"--\r\n"
    return bytes(buf)


def test_parse_multipart_extracts_named_parts():
    body = _build_multipart(
        "test-boundary",
        [
            ("stats", "application/json", b'{"runs_added": 3}'),
            ("user_db", "application/octet-stream", b"\x00\x01\x02BINARY"),
        ],
    )
    parts = geo_history._parse_multipart(body, "test-boundary")
    assert set(parts.keys()) == {"stats", "user_db"}
    assert parts["stats"] == b'{"runs_added": 3}'
    assert parts["user_db"] == b"\x00\x01\x02BINARY"


def test_parse_multipart_handles_binary_with_crlf_inside():
    # DuckDB binaries contain arbitrary bytes including \r\n. The parser must
    # not split on those — it only splits on the boundary line.
    payload = b"\r\n--fake-not-boundary--\r\n\x00\xff" * 10
    body = _build_multipart(
        "real-boundary",
        [
            ("stats", "application/json", b"{}"),
            ("user_db", "application/octet-stream", payload),
        ],
    )
    parts = geo_history._parse_multipart(body, "real-boundary")
    assert parts["user_db"] == payload


def test_parse_multipart_empty_body_returns_empty():
    body = _build_multipart("b", [])
    parts = geo_history._parse_multipart(body, "b")
    assert parts == {}
