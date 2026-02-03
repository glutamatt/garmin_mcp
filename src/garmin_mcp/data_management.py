"""
Data management functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""
import json

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all data management tools with the MCP server app"""

    @app.tool()
    async def add_body_composition(
        date: str,
        weight: float,
        ctx: Context,
        percent_fat: float = None,
        muscle_mass: float = None,
        bone_mass: float = None,
        bmi: float = None
    ) -> str:
        """Add body composition data

        Args:
            date: Date (YYYY-MM-DD)
            weight: Weight in kg
            percent_fat: Body fat percentage
            muscle_mass: Muscle mass
            bone_mass: Bone mass
            bmi: Body Mass Index
        """
        try:
            client = await get_client(ctx)
            result = client.add_body_composition(
                date,
                weight=weight,
                percent_fat=percent_fat,
                muscle_mass=muscle_mass,
                bone_mass=bone_mass,
                bmi=bmi
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def set_blood_pressure(
        systolic: int,
        diastolic: int,
        pulse: int,
        ctx: Context,
        notes: str = None
    ) -> str:
        """Set blood pressure values

        Args:
            systolic: Systolic pressure (top number)
            diastolic: Diastolic pressure (bottom number)
            pulse: Pulse rate
            notes: Optional notes
        """
        try:
            client = await get_client(ctx)
            result = client.set_blood_pressure(systolic, diastolic, pulse, notes=notes)
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def add_hydration_data(
        value_in_ml: int,
        cdate: str,
        timestamp: str,
        ctx: Context
    ) -> str:
        """Add hydration data

        Args:
            value_in_ml: Amount of liquid in ml
            cdate: Date (YYYY-MM-DD)
            timestamp: Timestamp (YYYY-MM-DDThh:mm:ss.sss)
        """
        try:
            client = await get_client(ctx)
            result = client.add_hydration_data(
                value_in_ml=value_in_ml,
                cdate=cdate,
                timestamp=timestamp
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
