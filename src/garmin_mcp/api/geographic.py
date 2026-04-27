"""Geographic narrative via the geo-runner service.

Encapsulates the FIT-download → multipart-upload → geo-runner round trip into
a single function. Agents call one CLI command (`garmin geographic activity
<id>`) ; they never have to wire the FIT bytes to the geo-runner endpoint
themselves.

The FIT is consumed in-memory only. The narrative result is written to the
session sandbox so the agent gets back compact metadata (path + columns +
row count) rather than the full payload — same design as
`activities download`.
"""

import io
import json as _json
import os
import zipfile

import requests
from garminconnect import Garmin

# Service URL is hard-coded for now ; will move to env/flag once we have a
# concrete need (local geo-runner during dev, alternate Spaces, …).
GEO_RUNNER_URL = "https://glutamatt-geo-runner.hf.space"

# Output formats accepted by `geo-runner /api/analyze?format=…`. Subset
# exposed at HTTP level (no `text`, that's CLI-only on the geo-runner side).
SUPPORTED_FORMATS = ("tsv", "llm", "json")
# TSV is the most useful for agents : pandas/Sheets-friendly, structured,
# self-describing header — and writing to disk keeps the agent's context
# clean. LLM narrative stays available via --format llm when prose is wanted.
DEFAULT_FORMAT = "tsv"

# HF Space free tier sleeps after inactivity ; first call can wake-up cold
# (~30-60 s). Keep a generous timeout so the agent gets a clean error message
# rather than a connection abort mid-flight.
REQUEST_TIMEOUT_S = 90


def analyze_activity(
    client: Garmin,
    activity_id: int,
    fmt: str = DEFAULT_FORMAT,
    sandbox: str = "/tmp/garmin",
) -> dict:
    """Download the activity's FIT, POST to geo-runner, write the narrative
    to disk in the sandbox.

    Returns metadata only (path, format, size, columns/rows when applicable)
    — same design as `activities download`. Keeps the agent's context light
    and the actual narrative out-of-band on the filesystem.

    Raises a `RuntimeError` with context on any failure (Garmin download
    error, malformed zip, geo-runner non-2xx response, network timeout).
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format '{fmt}'. Use one of: {', '.join(SUPPORTED_FORMATS)}"
        )

    fit_bytes = _download_fit(client, activity_id)
    text = _post_to_geo_runner(activity_id, fit_bytes, fmt)
    return _write_and_describe(text, activity_id, fmt, sandbox)


def _download_fit(client: Garmin, activity_id: int) -> bytes:
    """Pull the ORIGINAL FIT from Garmin Connect and extract the .fit file
    from the surrounding zip. In-memory only."""
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


def _post_to_geo_runner(activity_id: int, fit_bytes: bytes, fmt: str) -> str:
    """POST the FIT bytes as multipart to geo-runner ; return the body text.
    Surfaces geo-runner's own error JSON when the call returns non-2xx."""
    try:
        resp = requests.post(
            f"{GEO_RUNNER_URL}/api/analyze",
            params={"format": fmt},
            files={
                "fit": (
                    f"activity_{activity_id}.fit",
                    fit_bytes,
                    "application/octet-stream",
                )
            },
            timeout=REQUEST_TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"geo-runner request failed: {e}")

    if not resp.ok:
        # geo-runner responds with a `{"error": "..."}` body on 4xx ; surface
        # that field when present, otherwise truncate the raw text.
        try:
            err = resp.json().get("error", resp.text)
        except ValueError:
            err = resp.text[:300]
        raise RuntimeError(f"geo-runner {resp.status_code}: {err}")

    return resp.text


# Maps the geo-runner format name to the file extension we use on disk.
_EXT_FOR_FORMAT = {"tsv": "tsv", "llm": "txt", "json": "json"}


def _write_and_describe(text: str, activity_id: int, fmt: str, sandbox: str) -> dict:
    """Persist the narrative to the session sandbox and build a metadata
    dict that's tight enough to fit in an agent's context.

    Per-format metadata :
      - tsv  : columns + rows (parsed from header line, comments skipped),
               separator + meta_comment (the # Run ... summary line)
      - llm  : summary (1st line) + spans (count of "@ X.XX km" lines)
      - json : summary (parsed from response JSON) + spans (len of array)
    """
    os.makedirs(sandbox, exist_ok=True)
    ext = _EXT_FOR_FORMAT[fmt]
    file_path = os.path.join(sandbox, f"geographic_{activity_id}.{ext}")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)

    meta = {
        "activity_id": activity_id,
        "format": fmt,
        "path": file_path,
        "size_kb": round(os.path.getsize(file_path) / 1024, 1),
    }

    if fmt == "tsv":
        lines = text.splitlines()
        comment_lines = [ln for ln in lines if ln.startswith("#")]
        data_lines = [ln for ln in lines if not ln.startswith("#")]
        if data_lines:
            meta["columns"] = data_lines[0].split("\t")
            meta["rows"] = max(len(data_lines) - 1, 0)  # exclude header
            meta["separator"] = "\\t"
        if comment_lines:
            meta["meta_comment"] = comment_lines[0].lstrip("# ").strip()

    elif fmt == "llm":
        lines = text.splitlines()
        if lines:
            meta["summary"] = lines[0].lstrip("# ").strip()
        meta["spans"] = sum(1 for ln in lines if " @ " in ln and " km " in ln)

    elif fmt == "json":
        try:
            parsed = _json.loads(text)
            meta["summary"] = parsed.get("summary", {})
            meta["spans"] = len(parsed.get("spans", []))
        except _json.JSONDecodeError:
            # Shouldn't happen — geo-runner always returns valid JSON in
            # this mode — but degrade gracefully if it does.
            meta["parse_error"] = "geo-runner JSON body could not be parsed"

    return meta
