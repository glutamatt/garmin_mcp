"""Route geographic history orchestrator — bridges Garmin Connect ↔ geo-runner.

Per-user DuckDB lives at ``/tmp/neural-runner/geo-history/<sanitized_user_id>.duckdb``,
synced bidirectionally to the HF dataset by the ``hf-storage-sync`` sidecar.
This module never touches HF directly — it only reads/writes the local path.

Two operations :

- :func:`update` — pull-list-download-ingest loop. Bounded to 10 activities
  per call so a single invocation stays short. Idempotent : repeated calls
  converge once ``runs_added`` stops moving (or the listing fits in one batch).
- :func:`query` — POST a query JSON to geo-runner and return the response.

The geo-runner endpoints (``/api/history/ingest``, ``/api/history/query``) are
multipart-in. ``ingest`` is also multipart-out (updated DB + stats), which we
parse with a small custom decoder.
"""

import io
import json
import os
import re
import zipfile
from datetime import date, timedelta

import duckdb
import requests
from garminconnect import Garmin

# ── Configuration ────────────────────────────────────────────────────────────

USER_DB_DIR = "/tmp/neural-runner/geo-history"
WINDOW_DAYS = 365
BATCH_LIMIT = 10
REQUEST_TIMEOUT_S = 120  # ingest is N FITs heavy ; allow generous timeout

# Default to the production geo-runner. Overridable for local dev / testing.
DEFAULT_GEO_RUNNER_URL = os.environ.get(
    "GEO_RUNNER_URL", "https://glutamatt-geo-runner.hf.space"
)


# ── Path resolution ──────────────────────────────────────────────────────────


def sanitize_user_id(user_id: str) -> str:
    """Same sanitation rule as ``frontend/src/lib/token-store.ts`` :
    replace ``:`` and ``@`` with ``__``. Keeps the geo-history filenames
    in sync with tokens/ for the same user.
    """
    return user_id.replace(":", "__").replace("@", "__")


def user_db_path(user_id: str) -> str:
    """Absolute path of the per-user DuckDB file."""
    return os.path.join(USER_DB_DIR, f"{sanitize_user_id(user_id)}.duckdb")


def current_user_id(client: Garmin) -> str:
    """Derive the canonical user_id from the authenticated Garmin client.

    Returns ``garmin:<email>`` matching the convention in
    ``frontend/src/lib/token-store.ts``. The Garmin CLI is auto-scoped to
    the current user — callers never pass user_id explicitly.

    Order of fallbacks :
      1. ``client.garth.username`` — set after ``garth.loads()`` rehydrates
         the OAuth state. This is the email used to log in.
      2. ``client.garth.profile['userName']`` — same value via the JWT
         profile dict if username attr is missing.
    """
    email = getattr(client.garth, "username", None)
    if not email:
        profile = getattr(client.garth, "profile", None) or {}
        email = profile.get("userName") or profile.get("emailAddress")
    if not email:
        raise RuntimeError(
            "Cannot derive user_id : garth client has no username "
            "(token may be malformed or not yet hydrated)"
        )
    return f"garmin:{email}"


# ── Local DB introspection ──────────────────────────────────────────────────


def _ensure_user_db(path: str) -> None:
    """Create an empty DuckDB file at ``path`` if missing. geo-runner runs
    the schema migration on first ingest, so we just need a valid file.
    """
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Touching the path via duckdb.connect creates a valid empty DB file
    # that the Rust ``duckdb`` crate can open on the geo-runner side.
    conn = duckdb.connect(path)
    conn.close()


def latest_day_in_db(path: str) -> str | None:
    """Return ``MAX(runs.day)`` as ISO date string, or ``None`` when the DB is
    empty, schema-less, or missing entirely.
    """
    if not os.path.exists(path):
        return None
    conn = duckdb.connect(path, read_only=True)
    try:
        # `runs` may not exist yet on a freshly initialized DB.
        try:
            row = conn.execute("SELECT MAX(day) FROM runs").fetchone()
        except duckdb.CatalogException:
            return None
        if not row or row[0] is None:
            return None
        return str(row[0])
    finally:
        conn.close()


# ── FIT download (shared with geographic.py) ─────────────────────────────────


def _download_fit(client: Garmin, activity_id: int) -> bytes:
    """Pull the ORIGINAL FIT from Garmin Connect and unwrap the ``.fit`` file
    from the surrounding zip.
    """
    try:
        zip_bytes = client.download_activity(
            str(activity_id),
            dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL,
        )
    except Exception as e:
        raise RuntimeError(
            f"Garmin download failed for activity {activity_id}: {e}"
        )
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            fit_names = [n for n in zf.namelist() if n.endswith(".fit")]
            if not fit_names:
                raise RuntimeError(
                    f"No .fit file inside the activity {activity_id} zip"
                )
            return zf.read(fit_names[0])
    except zipfile.BadZipFile as e:
        raise RuntimeError(
            f"Invalid zip from Garmin (activity {activity_id}): {e}"
        )


# ── Multipart decode ────────────────────────────────────────────────────────


def _parse_multipart(body: bytes, boundary: str) -> dict[str, bytes]:
    """Parse a ``multipart/form-data`` response body into ``{name: bytes}``.

    Built to consume the exact shape geo-runner produces in ``server.rs`` —
    we control both sides, so we don't need a full general-purpose parser.
    """
    delim = b"--" + boundary.encode("ascii")
    parts = body.split(delim)
    result: dict[str, bytes] = {}
    # Skip preamble (parts[0]) and closing delim (parts[-1]).
    for part in parts[1:-1]:
        if not part.startswith(b"\r\n"):
            continue
        try:
            headers_blob, body_part = part[2:].split(b"\r\n\r\n", 1)
        except ValueError:
            continue
        body_part = body_part.rstrip(b"\r\n")
        for line in headers_blob.split(b"\r\n"):
            if line.lower().startswith(b"content-disposition:"):
                m = re.search(rb'name="([^"]+)"', line)
                if m:
                    result[m.group(1).decode("ascii")] = body_part
                break
    return result


# ── Update orchestrator ─────────────────────────────────────────────────────


def update(
    client: Garmin,
    geo_runner_url: str | None = None,
    limit: int = BATCH_LIMIT,
) -> dict:
    """Pull the user DB locally, list new Garmin activities since the
    convergent floor, download their FITs, batch-ingest into the user DB
    via geo-runner, and write the updated DB back.

    User identity is derived from the authenticated client — the CLI is
    auto-scoped to the current user.

    Convergence : the local DB is the source of truth. ``start`` is
    ``max(today - 1y, latest_day_in_db)``. Repeated calls walk forward
    until the listing returns ≤ ``limit`` activities (``is_caught_up``).

    Returns a stats dict with ``runs_added``, ``runs_skipped``, ``visits_added``,
    ``errors``, ``start``, ``batch_size``, ``activities_remaining``,
    ``is_caught_up``.
    """
    url = geo_runner_url or DEFAULT_GEO_RUNNER_URL
    user_id = current_user_id(client)
    path = user_db_path(user_id)
    _ensure_user_db(path)

    floor = (date.today() - timedelta(days=WINDOW_DAYS)).isoformat()
    latest = latest_day_in_db(path)
    start = max(floor, latest) if latest else floor

    # Garmin's `get_activities_by_date` returns newest-first by default. We
    # want oldest-first so we walk forward chronologically — sort manually.
    # Restrict to running activities ; widen later if we need to track other
    # sports.
    try:
        activities = client.get_activities_by_date(
            start, date.today().isoformat(), activitytype="running"
        )
    except Exception as e:
        raise RuntimeError(f"Garmin list_activities failed: {e}")

    activities.sort(key=lambda a: a.get("startTimeLocal", ""))
    batch = activities[:limit]

    if not batch:
        return {
            "runs_added": 0,
            "runs_skipped": 0,
            "visits_added": 0,
            "errors": [],
            "start": start,
            "batch_size": 0,
            "activities_remaining": 0,
            "is_caught_up": True,
        }

    # Build the multipart payload : user_db + N fits + metadata JSON array.
    fit_parts: list[tuple[str, bytes]] = []
    metadata: list[dict] = []
    errors: list[dict] = []
    for a in batch:
        aid = a.get("activityId")
        try:
            fit_bytes = _download_fit(client, aid)
        except Exception as e:
            errors.append({"activity_id": aid, "error": str(e)})
            continue
        fit_parts.append((f"activity_{aid}.fit", fit_bytes))
        metadata.append(
            {
                "source": "garmin",
                "source_activity_id": str(aid),
                "sport": (a.get("activityType") or {}).get("typeKey"),
                "distance_m": int(a.get("distance") or 0),
                "duration_s": int(a.get("duration") or 0),
            }
        )

    if not fit_parts:
        return {
            "runs_added": 0,
            "runs_skipped": 0,
            "visits_added": 0,
            "errors": errors,
            "start": start,
            "batch_size": 0,
            "activities_remaining": max(0, len(activities) - limit),
            "is_caught_up": len(activities) <= limit,
        }

    with open(path, "rb") as f:
        user_db_bytes = f.read()

    files = [("user_db", ("user.duckdb", user_db_bytes, "application/octet-stream"))]
    for name, body in fit_parts:
        files.append(("fits", (name, body, "application/octet-stream")))
    data = {"metadata": json.dumps(metadata)}

    try:
        resp = requests.post(
            f"{url}/api/history/ingest",
            files=files,
            data=data,
            timeout=REQUEST_TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"geo-runner ingest request failed: {e}")

    if not resp.ok:
        # geo-runner returns `{"error": "..."}` on 4xx ; surface that field
        # when present, otherwise truncate raw text.
        try:
            err = resp.json().get("error", resp.text)
        except ValueError:
            err = resp.text[:300]
        raise RuntimeError(f"geo-runner ingest {resp.status_code}: {err}")

    # Decode multipart response : updated user_db + stats JSON.
    ct = resp.headers.get("Content-Type", "")
    m = re.search(r"boundary=([^;]+)", ct)
    if not m:
        raise RuntimeError(
            f"ingest response has no multipart boundary; Content-Type={ct!r}"
        )
    parts = _parse_multipart(resp.content, m.group(1))
    if "user_db" not in parts or "stats" not in parts:
        raise RuntimeError(
            f"ingest response missing parts: got {list(parts.keys())}"
        )

    with open(path, "wb") as f:
        f.write(parts["user_db"])

    stats = json.loads(parts["stats"])
    return {
        **stats,
        "errors": stats.get("errors", []) + errors,
        "start": start,
        "batch_size": len(fit_parts),
        "activities_remaining": max(0, len(activities) - limit),
        "is_caught_up": len(activities) <= limit,
    }


# ── Query ───────────────────────────────────────────────────────────────────


def query_to_tsv(
    client: Garmin,
    kind: str,
    params: dict | None = None,
    sandbox: str = "/tmp/garmin",
    geo_runner_url: str | None = None,
    include_anonymous: bool = False,
) -> dict:
    """Run a heatmap query and write the (geometry-stripped, optionally
    anonymous-stripped) results to a TSV file in the session sandbox.
    Returns a metadata dict — same shape as ``geographic activity`` so
    Apex's context stays light.
    """
    resp = query(
        client, kind, params=params, geo_runner_url=geo_runner_url,
        include_anonymous=include_anonymous,
        with_geometry=False,
    )
    results = resp.get("results") or []
    data_as_of = resp.get("data_as_of") or "never"

    os.makedirs(sandbox, exist_ok=True)
    suffix = f"_{kind}"
    if params:
        bits = []
        if params.get("since"):
            bits.append(f"from{params['since']}")
        if params.get("until"):
            bits.append(f"to{params['until']}")
        if params.get("exclusive"):
            bits.append("excl")
        if bits:
            suffix += "_" + "_".join(bits)
    path = os.path.join(sandbox, f"geographic_history{suffix}.tsv")

    columns = ["count", "last_day", "entity_type", "relation", "display"]
    with open(path, "w", encoding="utf-8") as f:
        param_summary = " ".join(f"{k}={v}" for k, v in (params or {}).items()) or "(no filters)"
        f.write(
            f"# {kind} · {len(results)} entities · "
            f"data_as_of {data_as_of} · {param_summary}\n"
        )
        f.write("\t".join(columns) + "\n")
        for r in results:
            f.write(
                f"{r['count']}\t{r['last_day']}\t"
                f"{r['entity_type']}\t{r['relation']}\t{r['display']}\n"
            )

    return {
        "kind": kind,
        "format": "tsv",
        "path": path,
        "size_kb": round(os.path.getsize(path) / 1024, 1),
        "separator": "\\t",
        "columns": columns,
        "rows": len(results),
        "data_as_of": resp.get("data_as_of"),
        "params": params or {},
        # Top-5 preview so Apex can answer light questions without reading
        # the file. Sorted by count desc (the server already returns them so).
        "top_5": [
            {
                "count": r["count"],
                "display": r["display"],
                "entity_type": r["entity_type"],
                "relation": r["relation"],
                "last_day": r["last_day"],
            }
            for r in results[:5]
        ],
    }


def query(
    client: Garmin,
    kind: str,
    params: dict | None = None,
    geo_runner_url: str | None = None,
    include_anonymous: bool = False,
    with_geometry: bool = False,
) -> dict:
    """POST a query against the user DB and return the response JSON.

    User identity is derived from the authenticated client — the CLI is
    auto-scoped to the current user. The ``client`` arg is used ONLY to
    resolve the user_id (no Garmin API calls happen here).

    ``kind`` is currently restricted to ``"heatmap"`` ; ``params`` is the
    optional inner object (``since``, ``until``, ``exclusive``,
    ``entity_types``).

    Post-processing :
      - ``include_anonymous=False`` (default) drops results whose ``display``
        starts with ``"("`` — the synthetic fallback for OSM features
        without a ``name`` tag (``(Forêt)``, ``(chemin piéton)``, etc.,
        and their parent-enriched variants). Keeps the output focused on
        named places.
      - ``with_geometry=False`` (default) strips the ``geometry`` field from
        every result. A single heatmap response can be 3k+ entities × a
        polygon GeoJSON each ≈ 1.7M tokens — fatal for agent context.
        Only flip to True for direct rendering (the web UI hits the HTTP
        endpoint directly, not this helper).
    """
    url = geo_runner_url or DEFAULT_GEO_RUNNER_URL
    user_id = current_user_id(client)
    path = user_db_path(user_id)
    _ensure_user_db(path)

    with open(path, "rb") as f:
        user_db_bytes = f.read()

    query_obj = {"kind": kind, **(params or {})}
    files = {
        "user_db": ("user.duckdb", user_db_bytes, "application/octet-stream"),
        "query": (
            "query.json",
            json.dumps(query_obj).encode("utf-8"),
            "application/json",
        ),
    }

    try:
        resp = requests.post(
            f"{url}/api/history/query",
            files=files,
            timeout=REQUEST_TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"geo-runner query request failed: {e}")

    if not resp.ok:
        try:
            err = resp.json().get("error", resp.text)
        except ValueError:
            err = resp.text[:300]
        raise RuntimeError(f"geo-runner query {resp.status_code}: {err}")

    data = resp.json()
    results = data.get("results") or []
    if not include_anonymous:
        # Drop synthetic-display entries — OSM features without a `name` tag
        # get a `(type)` fallback or `(type) / Parent`. Useful in the map UI,
        # noise in agent context.
        results = [r for r in results if not (r.get("display") or "").startswith("(")]
    if not with_geometry:
        # Strip the per-row GeoJSON blob. A heatmap with 3k+ entities easily
        # crosses 1M tokens of geometries — fatal for the agent's context.
        results = [{k: v for k, v in r.items() if k != "geometry"} for r in results]
    data["results"] = results
    return data
