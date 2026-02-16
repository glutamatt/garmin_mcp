"""
Body data tools — weight, blood pressure, hydration (5 tools).

Merges weight_management + data_management into a single module.
Thin MCP wrappers over Garmin Connect body data APIs.
"""
import json
from typing import Optional

from fastmcp import Context
from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register body data tools with the MCP server app."""

    @app.tool()
    async def get_weigh_ins(start_date: str, end_date: str, ctx: Context) -> str:
        """Get weight measurements between specified dates.

        Returns weight in grams, BMI, body fat %, body water %, bone mass, muscle mass.
        For a single day, use the same date for both start and end.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            weigh_ins = get_client(ctx).get_weigh_ins(start_date, end_date)
            if not weigh_ins:
                return json.dumps({"error": f"No weight measurements found between {start_date} and {end_date}."})

            curated = {
                "count": len(weigh_ins),
                "date_range": {"start": start_date, "end": end_date},
                "measurements": [],
            }
            for w in weigh_ins:
                m = {
                    "date": w.get("date") or w.get("calendarDate"),
                    "weight_grams": w.get("weight"),
                    "bmi": w.get("bmi"),
                    "body_fat_percent": w.get("bodyFat"),
                    "body_water_percent": w.get("bodyWater"),
                    "bone_mass_grams": w.get("boneMass"),
                    "muscle_mass_grams": w.get("muscleMass"),
                    "source_type": w.get("sourceType"),
                    "timestamp": w.get("timestampLocal") or w.get("timestampGMT"),
                }
                curated["measurements"].append({k: v for k, v in m.items() if v is not None})

            return json.dumps(curated, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    async def add_weigh_in(
        weight: float,
        ctx: Context,
        unit_key: str = "kg",
        date_timestamp: Optional[str] = None,
        gmt_timestamp: Optional[str] = None,
    ) -> str:
        """Add a new weight measurement.

        Without timestamps, records at the current time.
        With timestamps, records at the specified time (useful for backdating).

        Args:
            weight: Weight value in the specified unit (e.g. 75.5 for kg, 166.4 for lb)
            unit_key: Unit of weight: 'kg' (default) or 'lb'
            date_timestamp: Optional local timestamp YYYY-MM-DDThh:mm:ss (for backdating)
            gmt_timestamp: Optional GMT timestamp YYYY-MM-DDThh:mm:ss (for backdating)
        """
        try:
            client = get_client(ctx)
            if date_timestamp and gmt_timestamp:
                client.add_weigh_in_with_timestamps(
                    weight=weight, unitKey=unit_key,
                    dateTimestamp=date_timestamp, gmtTimestamp=gmt_timestamp,
                )
            else:
                client.add_weigh_in(weight=weight, unitKey=unit_key)

            result = {"status": "success", "weight": weight, "unit": unit_key}
            if date_timestamp:
                result["timestamp_local"] = date_timestamp
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    async def delete_weigh_ins(date: str, ctx: Context, delete_all: bool = True) -> str:
        """Delete weight measurements for a specific date.

        Args:
            date: Date in YYYY-MM-DD format
            delete_all: Whether to delete all measurements for the day
        """
        try:
            get_client(ctx).delete_weigh_ins(date, delete_all=delete_all)
            return json.dumps({"status": "success", "date": date})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    async def set_blood_pressure(
        systolic: int, diastolic: int, pulse: int,
        ctx: Context, notes: Optional[str] = None,
    ) -> str:
        """Record a blood pressure measurement.

        Args:
            systolic: Systolic pressure in mmHg (top number, e.g. 120)
            diastolic: Diastolic pressure in mmHg (bottom number, e.g. 80)
            pulse: Pulse rate in bpm (e.g. 72)
            notes: Optional text notes about the measurement
        """
        try:
            result = get_client(ctx).set_blood_pressure(systolic, diastolic, pulse, notes=notes)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    async def add_hydration_data(
        value_in_ml: int, cdate: str, timestamp: str, ctx: Context,
    ) -> str:
        """Add hydration data.

        Args:
            value_in_ml: Amount of liquid in milliliters
            cdate: Date in YYYY-MM-DD format
            timestamp: Timestamp in YYYY-MM-DDThh:mm:ss.sss format
        """
        try:
            result = get_client(ctx).add_hydration_data(
                value_in_ml=value_in_ml, cdate=cdate, timestamp=timestamp,
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    return app
