"""Geographic narrative via the geo-runner service.

Encapsulates the FIT-download → multipart-upload → geo-runner round trip
into a single function. Agents call one CLI command (`garmin geographic
activity <id>`) and get back a small metadata dict pointing at the TSV file
on disk — same shape as `activities download`.

The FIT is consumed in-memory. The narrative is always written as TSV : the
format is pandas-ready (`pd.read_csv(path, sep='\\t', comment='#')`),
human-readable in `column -t -s $'\\t'`, and Sheets-safe (h:mm:ss durations).
No alternate formats — TSV covers every downstream use we have.
"""

import io
import os
import zipfile

import requests
from garminconnect import Garmin

# Service URL is hard-coded for now ; will move to env/flag once we have a
# concrete need (local geo-runner during dev, alternate Spaces, …).
GEO_RUNNER_URL = "https://glutamatt-geo-runner.hf.space"

# HF Space free tier sleeps after inactivity ; first call can wake-up cold
# (~30-60 s). Keep a generous timeout so the agent gets a clean error message
# rather than a connection abort mid-flight.
REQUEST_TIMEOUT_S = 90


def analyze_activity(
    client: Garmin,
    activity_id: int,
    sandbox: str = "/tmp/garmin",
) -> dict:
    """Download the activity's FIT, POST to geo-runner, write the TSV
    narrative to disk in the sandbox.

    Returns metadata only (path, size, columns, rows, separator, meta_comment)
    — same design as `activities download`. The agent's context stays light ;
    a `pd.read_csv(path, sep='\\t', comment='#')` opens the file in one line.

    Raises a `RuntimeError` with context on any failure (Garmin download
    error, malformed zip, geo-runner non-2xx response, network timeout).
    """
    fit_bytes = _download_fit(client, activity_id)
    text = _post_to_geo_runner(activity_id, fit_bytes)
    return _write_and_describe(text, activity_id, sandbox)


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


def _post_to_geo_runner(activity_id: int, fit_bytes: bytes) -> str:
    """POST the FIT bytes as multipart to geo-runner ; return the TSV body.
    Surfaces geo-runner's own error JSON when the call returns non-2xx."""
    try:
        resp = requests.post(
            f"{GEO_RUNNER_URL}/api/analyze",
            params={"format": "tsv"},
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


def _write_and_describe(text: str, activity_id: int, sandbox: str) -> dict:
    """Persist the TSV to the session sandbox and build a metadata dict
    that's tight enough to fit in an agent's context.

    The TSV body is structured as :
        # Run YYYY-MM-DD — X.XX km en H:MM:SS · D+Xm/-Ym · N spans   ← meta
        col1\\tcol2\\t…\\tcolN                                        ← header
        row1\\t…
        ...
    """
    os.makedirs(sandbox, exist_ok=True)
    file_path = os.path.join(sandbox, f"geographic_{activity_id}.tsv")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)

    meta = {
        "activity_id": activity_id,
        "format": "tsv",
        "path": file_path,
        "size_kb": round(os.path.getsize(file_path) / 1024, 1),
        "separator": "\\t",
    }

    lines = text.splitlines()
    comment_lines = [ln for ln in lines if ln.startswith("#")]
    data_lines = [ln for ln in lines if not ln.startswith("#")]
    if data_lines:
        meta["columns"] = data_lines[0].split("\t")
        meta["rows"] = max(len(data_lines) - 1, 0)  # exclude header
    if comment_lines:
        meta["meta_comment"] = comment_lines[0].lstrip("# ").strip()

    return meta
