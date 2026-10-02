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

import os

from garminconnect import Garmin
from garmin_mcp.api import geo_runner
from garmin_mcp.api.activities import download_fit


def analyze_activity(client: Garmin, activity_id: int, path: str) -> dict:
    """Download the activity's FIT, POST it to geo-runner, write the TSV
    narrative at `path`.

    Returns metadata only (path, size, columns, rows, separator, meta_comment)
    — same design as `activities download`. The agent's context stays light ;
    a `pd.read_csv(path, sep='\\t', comment='#')` opens the file in one line.

    Failures (Garmin download, geo-runner still waking up, geo-runner error):
    see `api/geo_runner.py` and `api/contract.py`.
    """
    fit_bytes = download_fit(client, activity_id)
    resp = geo_runner.post(
        "/api/analyze",
        "geo-runner analyze",
        params={"format": "tsv"},
        files={
            "fit": (f"activity_{activity_id}.fit", fit_bytes, "application/octet-stream")
        },
    )
    return _write_and_describe(resp.text, activity_id, path)


def _write_and_describe(text: str, activity_id: int, file_path: str) -> dict:
    """Persist the TSV at `file_path` and build a metadata dict
    that's tight enough to fit in an agent's context.

    The TSV body is structured as :
        # Run YYYY-MM-DD — X.XX km en H:MM:SS · D+Xm/-Ym · N spans   ← meta
        col1\\tcol2\\t…\\tcolN                                        ← header
        row1\\t…
        ...
    """
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
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
