"""
Activity tools — MCP registration layer.

Thin wrappers: get_client → api call → json.dumps.
6 tools (was 13 in activity_management.py).
"""

import json
import os
import zipfile

from fastmcp import Context
from garminconnect import Garmin
from garmin_mcp.client_factory import get_client
from garmin_mcp.api import activities as api


def register_tools(app):
    """Register all activity tools with the MCP server app."""

    @app.tool()
    async def get_activities(
        ctx: Context,
        start_date: str = None,
        end_date: str = None,
        activity_type: str = "",
        start: int = 0,
        limit: int = 20,
        include_hr_zones: bool = False,
    ) -> str:
        """Get activities by date range OR pagination.

        For date-based: provide start_date + end_date (+ optional activity_type filter).
        For pagination: provide start index + limit (newest first).

        Each activity includes training_effect, training_load (EPOC), power, VO2max, and inline HR zones (z1-z5).
        Set include_hr_zones=true to fetch detailed zone data via extra API calls
        (only for activities missing inline zones).

        Args:
            start_date: Start date in YYYY-MM-DD format (date range mode)
            end_date: End date in YYYY-MM-DD format (date range mode)
            activity_type: Optional filter (e.g., 'running', 'cycling')
            start: Starting index for pagination (default 0)
            limit: Max activities to return (default 20, max 100)
            include_hr_zones: Include time-in-zone breakdown per activity (default false)
        """
        try:
            return json.dumps(
                api.get_activities(get_client(ctx), start_date, end_date, activity_type, start, limit, include_hr_zones),
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_activity(activity_id: int, ctx: Context) -> str:
        """Detailed activity info: timing, distance, HR, cadence, power, training effect, weather.

        Use get_activities to find activity IDs first.

        Args:
            activity_id: Numeric activity ID
        """
        try:
            return json.dumps(api.get_activity(get_client(ctx), activity_id), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_activity_splits(activity_id: int, ctx: Context) -> str:
        """Per-lap splits: distance, duration, pace, HR, cadence, power per lap.

        Args:
            activity_id: Numeric activity ID
        """
        try:
            return json.dumps(api.get_activity_splits(get_client(ctx), activity_id), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_activity_hr_in_timezones(activity_id: int, ctx: Context) -> str:
        """Time spent in each heart rate zone (zone 1-5) during an activity.

        Args:
            activity_id: Numeric activity ID
        """
        try:
            return json.dumps(api.get_activity_hr_in_timezones(get_client(ctx), activity_id), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_activity_types(ctx: Context) -> str:
        """All available activity type codes (reference data for filtering)."""
        try:
            return json.dumps(api.get_activity_types(get_client(ctx)), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def download_activity(
        activity_id: int,
        ctx: Context,
        format: str = "fit",
    ) -> str:
        """Download activity file to disk. Returns file path — use execute_python to analyze.

        FIT = original recording (second-by-second HR, pace, cadence, power, GPS).
        GPX/TCX = XML exports (lighter, interoperable).

        The file is written to /tmp. Analyze with execute_python + fitparse (FIT)
        or xml.etree (GPX/TCX). NEVER print full file contents — summarize on disk.

        Args:
            activity_id: Numeric activity ID
            format: File format: 'fit' (default, recommended), 'gpx', or 'tcx'
        """
        try:
            client = get_client(ctx)
            fmt = format.lower().strip()

            format_map = {
                "fit": Garmin.ActivityDownloadFormat.ORIGINAL,
                "gpx": Garmin.ActivityDownloadFormat.GPX,
                "tcx": Garmin.ActivityDownloadFormat.TCX,
            }
            if fmt not in format_map:
                return json.dumps({"error": f"Unsupported format '{fmt}'. Use: fit, gpx, tcx"}, indent=2)

            content = client.download_activity(str(activity_id), dl_fmt=format_map[fmt])

            if fmt == "fit":
                # ORIGINAL returns a zip containing the .fit file
                zip_path = f"/tmp/activity_{activity_id}.zip"
                with open(zip_path, "wb") as f:
                    f.write(content)
                # Extract .fit from zip
                with zipfile.ZipFile(zip_path, "r") as zf:
                    fit_names = [n for n in zf.namelist() if n.endswith(".fit")]
                    if not fit_names:
                        return json.dumps({"error": "No .fit file found in downloaded zip"}, indent=2)
                    out_path = f"/tmp/activity_{activity_id}.fit"
                    with open(out_path, "wb") as f:
                        f.write(zf.read(fit_names[0]))
                os.remove(zip_path)
                file_path = out_path
            else:
                ext = fmt
                file_path = f"/tmp/activity_{activity_id}.{ext}"
                with open(file_path, "wb") as f:
                    f.write(content)

            size_kb = round(os.path.getsize(file_path) / 1024, 1)
            return json.dumps({
                "activity_id": activity_id,
                "format": fmt,
                "path": file_path,
                "size_kb": size_kb,
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    return app
