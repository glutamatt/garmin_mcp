"""
Training and performance functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""
import json
import datetime
from typing import Optional

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all training-related tools with the MCP server app"""

    @app.tool()
    async def get_training_status(date: str, ctx: Context) -> str:
        """Get training status with load, VO2 max, and recovery

        Args:
            date: Date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            status = client.get_training_status(date)
            if not status:
                return f"No training status for {date}"

            recent = status.get("mostRecentTrainingStatus", {})
            latest = recent.get("latestTrainingStatusData", {})
            device_data = next(iter(latest.values()), {})
            acwr = device_data.get("acuteTrainingLoadDTO", {})
            vo2 = status.get("mostRecentVO2Max", {}).get("generic", {})

            curated = {
                "date": date,
                "training_status": device_data.get("trainingStatus"),
                "feedback": device_data.get("trainingStatusFeedbackPhrase"),
                "acute_load": acwr.get("dailyTrainingLoadAcute"),
                "chronic_load": acwr.get("dailyTrainingLoadChronic"),
                "load_ratio": acwr.get("dailyAcuteChronicWorkloadRatio"),
                "vo2_max": vo2.get("vo2MaxValue"),
            }
            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_hrv_data(date: str, ctx: Context) -> str:
        """Get HRV (Heart Rate Variability) data

        Args:
            date: Date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            hrv = client.get_hrv_data(date)
            if not hrv:
                return f"No HRV data for {date}"

            summary = hrv.get("hrvSummary", {})
            baseline = summary.get("baseline", {})

            curated = {
                "date": date,
                "last_night_avg_ms": summary.get("lastNightAvg"),
                "last_night_5min_high_ms": summary.get("lastNight5MinHigh"),
                "weekly_avg_ms": summary.get("weeklyAvg"),
                "baseline_low_ms": baseline.get("balancedLow"),
                "baseline_upper_ms": baseline.get("balancedUpper"),
                "status": summary.get("status"),
                "feedback": summary.get("feedbackPhrase"),
            }
            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_hill_score(start_date: str, end_date: str, ctx: Context) -> str:
        """Get hill score data between dates

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            data = client.get_hill_score(start_date, end_date)
            if not data:
                return f"No hill score data between {start_date} and {end_date}"

            daily = data.get("hillScoreDTOList", [])
            latest = daily[0] if daily else {}

            curated = {
                "period_avg": next(iter(data.get("periodAvgScore", {}).values()), None),
                "max_score": data.get("maxScore"),
                "latest_date": latest.get("calendarDate"),
                "latest_overall": latest.get("overallScore"),
                "latest_strength": latest.get("strengthScore"),
                "latest_endurance": latest.get("enduranceScore"),
            }
            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_endurance_score(start_date: str, end_date: str, ctx: Context) -> str:
        """Get endurance score data between dates

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            data = client.get_endurance_score(start_date, end_date)
            if not data:
                return f"No endurance score data between {start_date} and {end_date}"

            score = data.get("enduranceScoreDTO", {})
            curated = {
                "period_avg": data.get("avg"),
                "period_max": data.get("max"),
                "current_score": score.get("overallScore"),
                "current_date": score.get("calendarDate"),
                "classification": score.get("classification"),
            }
            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_fitnessage_data(date: str, ctx: Context) -> str:
        """Get fitness age data

        Args:
            date: Date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            data = client.get_fitnessage_data(date)
            if not data:
                return f"No fitness age data for {date}"

            chrono = data.get("chronologicalAge")
            fitness = data.get("fitnessAge")
            curated = {
                "date": date,
                "fitness_age": round(fitness, 1) if fitness else None,
                "chronological_age": chrono,
                "difference": round(chrono - fitness, 1) if chrono and fitness else None,
                "achievable_fitness_age": data.get("achievableFitnessAge"),
            }
            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_training_effect(activity_id: int, ctx: Context) -> str:
        """Get training effect for an activity

        Args:
            activity_id: Activity ID
        """
        try:
            client = await get_client(ctx)
            activity = client.get_activity(activity_id)
            if not activity:
                return f"No activity {activity_id}"

            summary = activity.get("summaryDTO", {})
            curated = {
                "activity_id": activity_id,
                "aerobic_effect": summary.get("trainingEffect"),
                "anaerobic_effect": summary.get("anaerobicTrainingEffect"),
                "label": summary.get("trainingEffectLabel"),
                "training_load": summary.get("activityTrainingLoad"),
                "recovery_time_hours": round(summary.get("recoveryTime", 0) / 60, 1) if summary.get("recoveryTime") else None,
            }
            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_lactate_threshold(ctx: Context, start_date: str = None, end_date: str = None) -> str:
        """Get lactate threshold data

        Args:
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            if start_date and end_date:
                data = client.get_lactate_threshold(latest=False, start_date=start_date, end_date=end_date)
            else:
                data = client.get_lactate_threshold(latest=True)

            if not data:
                return "No lactate threshold data"

            if start_date and end_date:
                return json.dumps(data, indent=2)

            speed_hr = data.get("speed_and_heart_rate", {})
            power = data.get("power", {})
            curated = {
                "lactate_threshold_speed_mps": speed_hr.get("speed"),
                "lactate_threshold_hr_bpm": speed_hr.get("heartRate"),
                "functional_threshold_power_watts": power.get("functionalThresholdPower"),
                "power_to_weight": power.get("powerToWeight"),
            }
            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_progress_summary(start_date: str, end_date: str, metric: str, ctx: Context) -> str:
        """Get progress summary for a metric

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            metric: Metric (elevationGain, duration, distance, movingDuration)
        """
        try:
            client = await get_client(ctx)
            data = client.get_progress_summary_between_dates(start_date, end_date, metric)
            if not data:
                return f"No progress data for {metric}"

            if isinstance(data, list) and data:
                data = data[0]

            curated = {
                "metric": metric,
                "start_date": start_date,
                "end_date": end_date,
                "activity_count": data.get("countOfActivities"),
                "stats_by_type": {}
            }

            for activity_type, stats in data.get("stats", {}).items():
                if metric in stats and stats[metric].get("count", 0) > 0:
                    curated["stats_by_type"][activity_type] = {
                        "count": stats[metric].get("count"),
                        "sum": stats[metric].get("sum"),
                        "avg": stats[metric].get("avg"),
                    }

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
