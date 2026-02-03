"""
Health & Wellness Data functions for Garmin Connect MCP Server

Uses FastMCP Context for session - no token parameters needed.
Session must be set via garmin_login() or set_garmin_session() first.
"""
import json
import datetime

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all health and wellness tools with the MCP server app"""

    @app.tool()
    async def get_stats(date: str, ctx: Context) -> str:
        """Get daily activity stats with curated essential metrics

        Returns a summary of daily health and activity data including steps,
        calories, heart rate, stress, body battery, and sleep metrics.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            stats = client.get_stats(date)
            if not stats:
                return f"No stats found for {date}"

            summary = {
                "date": stats.get('calendarDate'),
                "total_steps": stats.get('totalSteps'),
                "daily_step_goal": stats.get('dailyStepGoal'),
                "distance_meters": stats.get('totalDistanceMeters'),
                "floors_ascended": round(stats.get('floorsAscended', 0), 1) if stats.get('floorsAscended') else None,
                "floors_descended": round(stats.get('floorsDescended', 0), 1) if stats.get('floorsDescended') else None,
                "total_calories": stats.get('totalKilocalories'),
                "active_calories": stats.get('activeKilocalories'),
                "bmr_calories": stats.get('bmrKilocalories'),
                "highly_active_seconds": stats.get('highlyActiveSeconds'),
                "active_seconds": stats.get('activeSeconds'),
                "sedentary_seconds": stats.get('sedentarySeconds'),
                "sleeping_seconds": stats.get('sleepingSeconds'),
                "moderate_intensity_minutes": stats.get('moderateIntensityMinutes'),
                "vigorous_intensity_minutes": stats.get('vigorousIntensityMinutes'),
                "intensity_minutes_goal": stats.get('intensityMinutesGoal'),
                "min_heart_rate_bpm": stats.get('minHeartRate'),
                "max_heart_rate_bpm": stats.get('maxHeartRate'),
                "resting_heart_rate_bpm": stats.get('restingHeartRate'),
                "last_7_days_avg_resting_hr": stats.get('lastSevenDaysAvgRestingHeartRate'),
                "avg_stress_level": stats.get('averageStressLevel'),
                "max_stress_level": stats.get('maxStressLevel'),
                "stress_qualifier": stats.get('stressQualifier'),
                "body_battery_charged": stats.get('bodyBatteryChargedValue'),
                "body_battery_drained": stats.get('bodyBatteryDrainedValue'),
                "body_battery_highest": stats.get('bodyBatteryHighestValue'),
                "body_battery_lowest": stats.get('bodyBatteryLowestValue'),
                "body_battery_current": stats.get('bodyBatteryMostRecentValue'),
                "avg_spo2_percent": stats.get('averageSpo2'),
                "lowest_spo2_percent": stats.get('lowestSpo2'),
                "avg_waking_respiration": stats.get('avgWakingRespirationValue'),
                "highest_respiration": stats.get('highestRespirationValue'),
                "lowest_respiration": stats.get('lowestRespirationValue'),
            }
            summary = {k: v for k, v in summary.items() if v is not None}
            return json.dumps(summary, indent=2)
        except Exception as e:
            return f"Error retrieving stats: {str(e)}"

    @app.tool()
    async def get_user_summary(date: str, ctx: Context) -> str:
        """Get user summary data

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            summary = client.get_user_summary(date)
            if not summary:
                return f"No user summary found for {date}"
            return json.dumps(summary, indent=2)
        except Exception as e:
            return f"Error retrieving user summary: {str(e)}"

    @app.tool()
    async def get_body_composition(start_date: str, ctx: Context, end_date: str = None) -> str:
        """Get body composition data for a single date or date range

        Args:
            start_date: Date in YYYY-MM-DD format or start date if end_date provided
            end_date: Optional end date in YYYY-MM-DD format for date range
        """
        try:
            client = await get_client(ctx)
            if end_date:
                composition = client.get_body_composition(start_date, end_date)
                if not composition:
                    return f"No body composition data found between {start_date} and {end_date}"
            else:
                composition = client.get_body_composition(start_date)
                if not composition:
                    return f"No body composition data found for {start_date}"
            return json.dumps(composition, indent=2)
        except Exception as e:
            return f"Error retrieving body composition data: {str(e)}"

    @app.tool()
    async def get_stats_and_body(date: str, ctx: Context) -> str:
        """Get stats and body composition data

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            data = client.get_stats_and_body(date)
            if not data:
                return f"No stats and body composition data found for {date}"
            return json.dumps(data, indent=2)
        except Exception as e:
            return f"Error retrieving stats and body composition data: {str(e)}"

    @app.tool()
    async def get_steps_data(date: str, ctx: Context) -> str:
        """Get detailed steps data with 15-minute intervals

        Note: Returns full interval data (~14KB). For compact summary, use get_stats().

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            steps_data = client.get_steps_data(date)
            if not steps_data:
                return f"No steps data found for {date}"
            return json.dumps(steps_data, indent=2)
        except Exception as e:
            return f"Error retrieving steps data: {str(e)}"

    @app.tool()
    async def get_daily_steps(start_date: str, end_date: str, ctx: Context) -> str:
        """Get steps data for a date range

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            steps_data = client.get_daily_steps(start_date, end_date)
            if not steps_data:
                return f"No daily steps data found between {start_date} and {end_date}"
            return json.dumps(steps_data, indent=2)
        except Exception as e:
            return f"Error retrieving daily steps data: {str(e)}"

    @app.tool()
    async def get_training_readiness(date: str, ctx: Context) -> str:
        """Get training readiness data with curated metrics

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            readiness_list = client.get_training_readiness(date)
            if not readiness_list:
                return f"No training readiness data found for {date}"

            curated = []
            for r in readiness_list:
                entry = {
                    "date": r.get('calendarDate'),
                    "timestamp": r.get('timestampLocal'),
                    "context": r.get('inputContext'),
                    "level": r.get('level'),
                    "score": r.get('score'),
                    "feedback": r.get('feedbackShort'),
                    "sleep_score": r.get('sleepScore'),
                    "sleep_factor_percent": r.get('sleepScoreFactorPercent'),
                    "recovery_time_hours": round(r.get('recoveryTime', 0) / 60, 1) if r.get('recoveryTime') else None,
                    "recovery_factor_percent": r.get('recoveryTimeFactorPercent'),
                    "training_load_factor_percent": r.get('acwrFactorPercent'),
                    "acute_load": r.get('acuteLoad'),
                    "hrv_factor_percent": r.get('hrvFactorPercent'),
                    "hrv_weekly_avg": r.get('hrvWeeklyAverage'),
                }
                entry = {k: v for k, v in entry.items() if v is not None}
                curated.append(entry)
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving training readiness data: {str(e)}"

    @app.tool()
    async def get_body_battery(start_date: str, end_date: str, ctx: Context) -> str:
        """Get body battery data with events

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            battery_data = client.get_body_battery(start_date, end_date)
            if not battery_data:
                return f"No body battery data found between {start_date} and {end_date}"

            curated = []
            for day in battery_data:
                entry = {
                    "date": day.get('date'),
                    "charged": day.get('charged'),
                    "drained": day.get('drained'),
                    "events": []
                }
                for event in day.get('bodyBatteryActivityEvent', []):
                    entry["events"].append({
                        "type": event.get('eventType'),
                        "start_time": event.get('eventStartTimeGmt'),
                        "duration_minutes": round(event.get('durationInMilliseconds', 0) / 60000, 1),
                        "body_battery_impact": event.get('bodyBatteryImpact'),
                        "feedback": event.get('shortFeedback'),
                    })
                feedback = day.get('bodyBatteryDynamicFeedbackEvent', {})
                if feedback:
                    entry["current_feedback"] = feedback.get('feedbackShortType')
                    entry["body_battery_level"] = feedback.get('bodyBatteryLevel')
                curated.append(entry)
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving body battery data: {str(e)}"

    @app.tool()
    async def get_sleep_data(date: str, ctx: Context) -> str:
        """Get full sleep data with all details

        Note: Returns detailed sleep data (~50KB). For compact summary, use get_sleep_summary().

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            sleep_data = client.get_sleep_data(date)
            if not sleep_data:
                return f"No sleep data found for {date}"
            return json.dumps(sleep_data, indent=2)
        except Exception as e:
            return f"Error retrieving sleep data: {str(e)}"

    @app.tool()
    async def get_sleep_summary(date: str, ctx: Context) -> str:
        """Get sleep summary with essential metrics (lightweight)

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            sleep_data = client.get_sleep_data(date)
            if not sleep_data:
                return f"No sleep summary found for {date}"

            summary = {}
            daily_sleep = sleep_data.get('dailySleepDTO', {})
            if daily_sleep:
                summary['sleep_seconds'] = daily_sleep.get('sleepTimeSeconds')
                summary['sleep_start'] = daily_sleep.get('sleepStartTimestampGMT')
                summary['sleep_end'] = daily_sleep.get('sleepEndTimestampGMT')
                summary['sleep_score'] = daily_sleep.get('sleepScores', {}).get('overall', {}).get('value')
                summary['deep_sleep_seconds'] = daily_sleep.get('deepSleepSeconds')
                summary['light_sleep_seconds'] = daily_sleep.get('lightSleepSeconds')
                summary['rem_sleep_seconds'] = daily_sleep.get('remSleepSeconds')
                summary['awake_seconds'] = daily_sleep.get('awakeSleepSeconds')
                summary['awake_count'] = daily_sleep.get('awakeCount')
                summary['avg_sleep_stress'] = daily_sleep.get('avgSleepStress')
                summary['resting_heart_rate_bpm'] = daily_sleep.get('restingHeartRate')

            spo2_summary = sleep_data.get('wellnessSpO2SleepSummaryDTO', {})
            if spo2_summary:
                summary['avg_spo2_percent'] = spo2_summary.get('averageSpo2')
                summary['lowest_spo2_percent'] = spo2_summary.get('lowestSpo2')

            if 'avgOvernightHrv' in sleep_data:
                summary['avg_overnight_hrv'] = sleep_data.get('avgOvernightHrv')

            total_sleep = summary.get('sleep_seconds', 0)
            if total_sleep and total_sleep > 0:
                summary['sleep_hours'] = round(total_sleep / 3600, 2)

            summary = {k: v for k, v in summary.items() if v is not None}
            return json.dumps(summary, indent=2)
        except Exception as e:
            return f"Error retrieving sleep summary: {str(e)}"

    @app.tool()
    async def get_stress_data(date: str, ctx: Context) -> str:
        """Get full stress time-series data

        Note: Returns detailed interval data (~35KB). For compact summary, use get_stress_summary().

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            stress_data = client.get_stress_data(date)
            if not stress_data:
                return f"No stress data found for {date}"
            return json.dumps(stress_data, indent=2)
        except Exception as e:
            return f"Error retrieving stress data: {str(e)}"

    @app.tool()
    async def get_stress_summary(date: str, ctx: Context) -> str:
        """Get stress summary with essential metrics (lightweight)

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            stress_data = client.get_stress_data(date)
            if not stress_data:
                return f"No stress data found for {date}"

            summary = {
                "date": stress_data.get('calendarDate'),
                "max_stress_level": stress_data.get('maxStressLevel'),
                "avg_stress_level": stress_data.get('avgStressLevel'),
            }

            stress_values = stress_data.get('stressValuesArray', [])
            if stress_values:
                valid_values = [v[1] for v in stress_values if v[1] and v[1] > 0]
                total = len(valid_values) if valid_values else 1
                summary["rest_percent"] = round(len([v for v in valid_values if v < 26]) / total * 100, 1)
                summary["low_stress_percent"] = round(len([v for v in valid_values if 26 <= v < 51]) / total * 100, 1)
                summary["medium_stress_percent"] = round(len([v for v in valid_values if 51 <= v < 76]) / total * 100, 1)
                summary["high_stress_percent"] = round(len([v for v in valid_values if v >= 76]) / total * 100, 1)

            summary = {k: v for k, v in summary.items() if v is not None}
            return json.dumps(summary, indent=2)
        except Exception as e:
            return f"Error retrieving stress summary: {str(e)}"

    @app.tool()
    async def get_heart_rates(date: str, ctx: Context) -> str:
        """Get full heart rate time-series data

        Note: Returns detailed 2-minute interval data (~25KB).

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            hr_data = client.get_heart_rates(date)
            if not hr_data:
                return f"No heart rate data found for {date}"
            return json.dumps(hr_data, indent=2)
        except Exception as e:
            return f"Error retrieving heart rate data: {str(e)}"

    @app.tool()
    async def get_hrv_data(date: str, ctx: Context) -> str:
        """Get HRV (Heart Rate Variability) data

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            hrv_data = client.get_hrv_data(date)
            if not hrv_data:
                return f"No HRV data found for {date}"

            summary = hrv_data.get("hrvSummary", {})
            baseline = summary.get("baseline", {})

            curated = {
                "date": summary.get("calendarDate") or date,
                "last_night_avg_hrv_ms": summary.get("lastNightAvg"),
                "last_night_5min_high_hrv_ms": summary.get("lastNight5MinHigh"),
                "weekly_avg_hrv_ms": summary.get("weeklyAvg"),
                "baseline_balanced_low_ms": baseline.get("balancedLow"),
                "baseline_balanced_upper_ms": baseline.get("balancedUpper"),
                "status": summary.get("status"),
                "feedback": summary.get("feedbackPhrase"),
            }
            curated = {k: v for k, v in curated.items() if v is not None}
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving HRV data: {str(e)}"

    @app.tool()
    async def get_spo2_data(date: str, ctx: Context) -> str:
        """Get SpO2 (blood oxygen) data

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            spo2_data = client.get_spo2_data(date)
            if not spo2_data:
                return f"No SpO2 data found for {date}"

            summary = {
                "date": spo2_data.get('calendarDate'),
                "avg_spo2_percent": spo2_data.get('averageSpO2'),
                "lowest_spo2_percent": spo2_data.get('lowestSpO2'),
                "latest_spo2_percent": spo2_data.get('latestSpO2'),
                "last_7_days_avg_spo2": spo2_data.get('lastSevenDaysAvgSpO2'),
                "avg_sleep_spo2_percent": spo2_data.get('avgSleepSpO2'),
            }
            summary = {k: v for k, v in summary.items() if v is not None}
            return json.dumps(summary, indent=2)
        except Exception as e:
            return f"Error retrieving SpO2 data: {str(e)}"

    @app.tool()
    async def get_respiration_data(date: str, ctx: Context) -> str:
        """Get respiration data

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            resp_data = client.get_respiration_data(date)
            if not resp_data:
                return f"No respiration data found for {date}"

            summary = {
                "date": resp_data.get('calendarDate'),
                "lowest_breaths_per_min": resp_data.get('lowestRespirationValue'),
                "highest_breaths_per_min": resp_data.get('highestRespirationValue'),
                "avg_waking_breaths_per_min": resp_data.get('avgWakingRespirationValue'),
                "avg_sleep_breaths_per_min": resp_data.get('avgSleepRespirationValue'),
            }
            summary = {k: v for k, v in summary.items() if v is not None}
            return json.dumps(summary, indent=2)
        except Exception as e:
            return f"Error retrieving respiration data: {str(e)}"

    @app.tool()
    async def get_hydration_data(date: str, ctx: Context) -> str:
        """Get hydration data

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            hydration_data = client.get_hydration_data(date)
            if not hydration_data:
                return f"No hydration data found for {date}"
            return json.dumps(hydration_data, indent=2)
        except Exception as e:
            return f"Error retrieving hydration data: {str(e)}"

    @app.tool()
    async def get_floors(date: str, ctx: Context) -> str:
        """Get floors climbed data

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            floors_data = client.get_floors(date)
            if not floors_data:
                return f"No floors data found for {date}"
            return json.dumps(floors_data, indent=2)
        except Exception as e:
            return f"Error retrieving floors data: {str(e)}"

    @app.tool()
    async def get_blood_pressure(start_date: str, end_date: str, ctx: Context) -> str:
        """Get blood pressure data

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            client = await get_client(ctx)
            bp_data = client.get_blood_pressure(start_date, end_date)
            if not bp_data:
                return f"No blood pressure data found between {start_date} and {end_date}"
            return json.dumps(bp_data, indent=2)
        except Exception as e:
            return f"Error retrieving blood pressure data: {str(e)}"

    return app
