"""
Weight management functions for Garmin Connect MCP Server
"""
import json
import datetime
from typing import Any, Dict, List, Optional, Union


from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all weight management tools with the MCP server app"""

    @app.tool()
    def get_weigh_ins(start_date: str, end_date: str) -> str:
        """Get weight measurements between specified dates

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            client = get_client()
            weigh_ins = client.get_weigh_ins(start_date, end_date)
            if not weigh_ins:
                return f"No weight measurements found between {start_date} and {end_date}."

            # Curate the response
            curated = {
                "count": len(weigh_ins),
                "date_range": {"start": start_date, "end": end_date},
                "measurements": []
            }

            for w in weigh_ins:
                measurement = {
                    "date": w.get('date') or w.get('calendarDate'),
                    "weight_grams": w.get('weight'),
                    "bmi": w.get('bmi'),
                    "body_fat_percent": w.get('bodyFat'),
                    "body_water_percent": w.get('bodyWater'),
                    "bone_mass_grams": w.get('boneMass'),
                    "muscle_mass_grams": w.get('muscleMass'),
                    "source_type": w.get('sourceType'),
                    "timestamp": w.get('timestampLocal') or w.get('timestampGMT'),
                }
                # Remove None values
                measurement = {k: v for k, v in measurement.items() if v is not None}
                curated["measurements"].append(measurement)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving weight measurements: {str(e)}"

    @app.tool()
    def get_daily_weigh_ins(date: str) -> str:
        """Get weight measurements for a specific date

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = get_client()
            weigh_ins = client.get_daily_weigh_ins(date)
            if not weigh_ins:
                return f"No weight measurements found for {date}."

            # Curate the response
            curated = {
                "date": date,
                "count": len(weigh_ins),
                "measurements": []
            }

            for w in weigh_ins:
                measurement = {
                    "weight_grams": w.get('weight'),
                    "bmi": w.get('bmi'),
                    "body_fat_percent": w.get('bodyFat'),
                    "body_water_percent": w.get('bodyWater'),
                    "bone_mass_grams": w.get('boneMass'),
                    "muscle_mass_grams": w.get('muscleMass'),
                    "source_type": w.get('sourceType'),
                    "timestamp": w.get('timestampLocal') or w.get('timestampGMT'),
                }
                # Remove None values
                measurement = {k: v for k, v in measurement.items() if v is not None}
                curated["measurements"].append(measurement)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving daily weight measurements: {str(e)}"

    @app.tool()
    def delete_weigh_ins(date: str, delete_all: bool = True) -> str:
        """Delete weight measurements for a specific date

        Args:
            date: Date in YYYY-MM-DD format
            delete_all: Whether to delete all measurements for the day
        """
        try:
            client = get_client()
            result = client.delete_weigh_ins(date, delete_all=delete_all)
            # Return structured response
            return json.dumps({
                "status": "success",
                "date": date,
                "message": f"Weight measurements deleted for {date}"
            }, indent=2)
        except Exception as e:
            return f"Error deleting weight measurements: {str(e)}"

    @app.tool()
    def add_weigh_in(weight: float, unit_key: str = "kg") -> str:
        """Add a new weight measurement

        Args:
            weight: Weight value
            unit_key: Unit of weight ('kg' or 'lb')
        """
        try:
            client = get_client()
            result = client.add_weigh_in(weight=weight, unitKey=unit_key)
            # Return structured response
            return json.dumps({
                "status": "success",
                "weight": weight,
                "unit": unit_key,
                "message": "Weight measurement added successfully"
            }, indent=2)
        except Exception as e:
            return f"Error adding weight measurement: {str(e)}"

    @app.tool()
    def add_weigh_in_with_timestamps(
        weight: float,
        
        unit_key: str = "kg",
        date_timestamp: str = None,
        gmt_timestamp: str = None
    ) -> str:
        """Add a new weight measurement with specific timestamps

        Args:
            weight: Weight value
            unit_key: Unit of weight ('kg' or 'lb')
            date_timestamp: Local timestamp in format YYYY-MM-DDThh:mm:ss
            gmt_timestamp: GMT timestamp in format YYYY-MM-DDThh:mm:ss
        """
        try:
            client = get_client()
            if date_timestamp is None or gmt_timestamp is None:
                # Generate timestamps if not provided
                now = datetime.datetime.now()
                date_timestamp = now.strftime('%Y-%m-%dT%H:%M:%S')
                gmt_timestamp = now.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

            result = client.add_weigh_in_with_timestamps(
                weight=weight,
                unitKey=unit_key,
                dateTimestamp=date_timestamp,
                gmtTimestamp=gmt_timestamp
            )
            # Return structured response
            return json.dumps({
                "status": "success",
                "weight": weight,
                "unit": unit_key,
                "timestamp_local": date_timestamp,
                "timestamp_gmt": gmt_timestamp,
                "message": "Weight measurement added successfully"
            }, indent=2)
        except Exception as e:
            return f"Error adding weight measurement with timestamps: {str(e)}"

    return app
