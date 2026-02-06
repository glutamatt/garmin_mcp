"""
Data management functions for Garmin Connect MCP Server
"""
import json
from typing import Optional

from fastmcp import Context
from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all data management tools with the MCP server app"""

    @app.tool()
    async def add_body_composition(
        date: str,
        weight: float,
        ctx: Context,
        percent_fat: Optional[float] = None,
        percent_hydration: Optional[float] = None,
        visceral_fat_mass: Optional[float] = None,
        bone_mass: Optional[float] = None,
        muscle_mass: Optional[float] = None,
        basal_met: Optional[float] = None,
        active_met: Optional[float] = None,
        physique_rating: Optional[int] = None,
        metabolic_age: Optional[float] = None,
        visceral_fat_rating: Optional[int] = None,
        bmi: Optional[float] = None
    ) -> str:
        """Add body composition data for a specific date.

        Args:
            date: Date in YYYY-MM-DD format
            weight: Weight in kg (e.g. 75.5)
            percent_fat: Body fat percentage (e.g. 18.5)
            percent_hydration: Hydration percentage (e.g. 55.0)
            visceral_fat_mass: Visceral fat mass in grams
            bone_mass: Bone mass in grams
            muscle_mass: Muscle mass in grams
            basal_met: Basal metabolic rate in kcal
            active_met: Active metabolic rate in kcal
            physique_rating: Physique rating (1-9 scale)
            metabolic_age: Metabolic age in years
            visceral_fat_rating: Visceral fat rating (1-59 scale)
            bmi: Body Mass Index (e.g. 24.5)
        """
        try:
            result = get_client(ctx).add_body_composition(
                date,
                weight=weight,
                percent_fat=percent_fat,
                percent_hydration=percent_hydration,
                visceral_fat_mass=visceral_fat_mass,
                bone_mass=bone_mass,
                muscle_mass=muscle_mass,
                basal_met=basal_met,
                active_met=active_met,
                physique_rating=physique_rating,
                metabolic_age=metabolic_age,
                visceral_fat_rating=visceral_fat_rating,
                bmi=bmi
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error adding body composition data: {str(e)}"
    
    @app.tool()
    async def set_blood_pressure(
        systolic: int,
        diastolic: int,
        pulse: int,
        ctx: Context,
        notes: Optional[str] = None
    ) -> str:
        """Record a blood pressure measurement.

        Args:
            systolic: Systolic pressure in mmHg (top number, e.g. 120)
            diastolic: Diastolic pressure in mmHg (bottom number, e.g. 80)
            pulse: Pulse rate in bpm (e.g. 72)
            notes: Optional text notes about the measurement
        """
        try:
            result = get_client(ctx).set_blood_pressure(
                systolic, diastolic, pulse, notes=notes
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error setting blood pressure values: {str(e)}"
    
    @app.tool()
    async def add_hydration_data(
        value_in_ml: int,
        cdate: str,
        timestamp: str,
        ctx: Context
    ) -> str:
        """Add hydration data
        
        Args:
            value_in_ml: Amount of liquid in milliliters
            cdate: Date in YYYY-MM-DD format
            timestamp: Timestamp in YYYY-MM-DDThh:mm:ss.sss format
        """
        try:
            result = get_client(ctx).add_hydration_data(
                value_in_ml=value_in_ml,
                cdate=cdate,
                timestamp=timestamp
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error adding hydration data: {str(e)}"

    return app