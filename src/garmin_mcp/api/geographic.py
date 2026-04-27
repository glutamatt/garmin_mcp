"""Geographic narrative via the geo-runner service.

Encapsulates the FIT-download → multipart-upload → geo-runner round trip into
a single function. Agents call one CLI command (`garmin geographic activity
<id>`) and get back the narrative ; they never have to wire the FIT bytes to
the geo-runner endpoint themselves.

The FIT is consumed in-memory only — never written to disk by this module.
"""

import io
import zipfile

import requests
from garminconnect import Garmin

# Service URL is hard-coded for now ; will move to env/flag once we have a
# concrete need (local geo-runner during dev, alternate Spaces, …).
GEO_RUNNER_URL = "https://glutamatt-geo-runner.hf.space"

# Output formats accepted by `geo-runner /api/analyze?format=…`. Subset
# exposed at HTTP level (no `text`, that's CLI-only on the geo-runner side).
SUPPORTED_FORMATS = ("llm", "tsv", "json")
DEFAULT_FORMAT = "llm"

# HF Space free tier sleeps after inactivity ; first call can wake-up cold
# (~30-60 s). Keep a generous timeout so the agent gets a clean error message
# rather than a connection abort mid-flight.
REQUEST_TIMEOUT_S = 90


def analyze_activity(client: Garmin, activity_id: int, fmt: str = DEFAULT_FORMAT) -> str:
    """Download the activity's FIT and POST it to geo-runner.

    Returns the response body as a string (LLM narrative, TSV table, or JSON
    payload depending on `fmt`). The caller decides whether to print it or
    write to disk via the global `--output` mechanism.

    Raises a `RuntimeError` with context on any failure (Garmin download
    error, malformed zip, geo-runner non-2xx response, network timeout).
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format '{fmt}'. Use one of: {', '.join(SUPPORTED_FORMATS)}"
        )

    fit_bytes = _download_fit(client, activity_id)
    return _post_to_geo_runner(activity_id, fit_bytes, fmt)


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
