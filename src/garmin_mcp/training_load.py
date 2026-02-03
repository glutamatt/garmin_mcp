"""
Training Load Analysis for Garmin Connect MCP Server

Provides ACWR (Acute:Chronic Workload Ratio) computation and training load metrics
that may not be available on lower-tier Garmin watches.

Based on the training-load-dataviz app by glutamatt.
"""
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastmcp import Context

from garmin_mcp.client_factory import get_client


# =============================================================================
# ACWR COMPUTATION LOGIC
# =============================================================================

def _calculate_hr_tss(
    duration_seconds: float,
    avg_hr: float,
    threshold_hr: float = 170,
    resting_hr: float = 50
) -> float:
    """Calculate TSS from heart rate when power data unavailable.

    Formula: HR-TSS = Duration(hours) × HR_Ratio² × 100
    Where HR_Ratio = (Avg HR - Resting HR) / (Threshold HR - Resting HR)
    """
    if not avg_hr or avg_hr <= resting_hr:
        return 0.0

    duration_hours = duration_seconds / 3600
    hr_ratio = (avg_hr - resting_hr) / (threshold_hr - resting_hr)
    return duration_hours * (hr_ratio ** 2) * 100


def _calculate_power_tss(
    duration_seconds: float,
    normalized_power: float,
    ftp: float = 250
) -> float:
    """Calculate TSS from power data.

    Formula: TSS = (Duration × NP × IF) / (FTP × 3600) × 100
    Where IF = NP / FTP
    """
    if not normalized_power or not ftp:
        return 0.0

    intensity_factor = normalized_power / ftp
    return (duration_seconds * normalized_power * intensity_factor) / (ftp * 3600) * 100


def _estimate_tss_from_activity(activity: dict, ftp: float = 250, threshold_hr: float = 170, resting_hr: float = 50) -> float:
    """Estimate TSS from an activity using available data.

    Priority:
    1. Use normalized power if available
    2. Fall back to average heart rate
    3. Fall back to duration-based estimate
    """
    duration = activity.get('duration') or activity.get('movingDuration') or 0

    # Try power-based TSS first
    np = activity.get('normPower') or activity.get('normalizedPower')
    if np and np > 0:
        return _calculate_power_tss(duration, np, ftp)

    # Try HR-based TSS
    avg_hr = activity.get('averageHR') or activity.get('avgHr')
    if avg_hr and avg_hr > 0:
        return _calculate_hr_tss(duration, avg_hr, threshold_hr, resting_hr)

    # Fallback: rough estimate based on duration (assumes moderate intensity)
    # 1 hour of moderate activity ≈ 50 TSS
    return (duration / 3600) * 50


def _aggregate_by_date(activities: List[dict], metric: str, **kwargs) -> Dict[str, float]:
    """Aggregate activity metric values by date.

    Args:
        activities: List of activity dicts
        metric: One of 'distance', 'duration', 'tss', 'calories'
        **kwargs: Additional params for TSS calculation (ftp, threshold_hr, resting_hr)

    Returns:
        Dict mapping date string (YYYY-MM-DD) to summed metric value
    """
    daily_values = {}

    for activity in activities:
        # Get activity date
        start_time = activity.get('startTimeLocal') or activity.get('startTimeGMT')
        if not start_time:
            continue

        # Parse date
        if isinstance(start_time, str):
            date_str = start_time[:10]  # YYYY-MM-DD
        else:
            date_str = start_time.strftime('%Y-%m-%d')

        # Get metric value
        if metric == 'distance':
            value = (activity.get('distance') or 0) / 1000  # Convert to km
        elif metric == 'duration':
            value = (activity.get('duration') or activity.get('movingDuration') or 0) / 60  # Convert to minutes
        elif metric == 'tss':
            value = _estimate_tss_from_activity(activity, **kwargs)
        elif metric == 'calories':
            value = activity.get('calories') or 0
        else:
            value = 0

        # Aggregate
        if date_str not in daily_values:
            daily_values[date_str] = 0
        daily_values[date_str] += value

    return daily_values


def _calculate_rolling_average(daily_values: Dict[str, float], end_date: str, days: int) -> Optional[float]:
    """Calculate rolling average for a date range.

    Args:
        daily_values: Dict mapping date to value
        end_date: End date (YYYY-MM-DD)
        days: Number of days to average (7 for acute, 28 for chronic)

    Returns:
        Average value or None if insufficient data
    """
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    total = 0
    count = 0

    for i in range(days):
        check_date = (end_dt - timedelta(days=i)).strftime('%Y-%m-%d')
        # Include 0 for rest days
        total += daily_values.get(check_date, 0)
        count += 1

    return total / count if count > 0 else None


def calculate_acwr(
    activities: List[dict],
    metric: str = 'tss',
    target_date: str = None,
    ftp: float = 250,
    threshold_hr: float = 170,
    resting_hr: float = 50
) -> dict:
    """Calculate ACWR (Acute:Chronic Workload Ratio) from activities.

    ACWR = 7-day average / 28-day average

    Risk zones:
    - < 0.8: Detraining risk (blue)
    - 0.8-1.3: Optimal zone (green)
    - 1.3-1.5: Warning zone (orange)
    - > 1.5: Injury risk (red)

    Args:
        activities: List of Garmin activity dicts
        metric: 'distance' (km), 'duration' (min), 'tss', or 'calories'
        target_date: Date to calculate ACWR for (default: most recent)
        ftp: Functional Threshold Power for TSS calculation
        threshold_hr: Threshold heart rate for HR-based TSS
        resting_hr: Resting heart rate for HR-based TSS

    Returns:
        Dict with ACWR value, risk zone, and component values
    """
    if not activities:
        return {"error": "No activities provided"}

    # Aggregate by date
    daily_values = _aggregate_by_date(
        activities, metric,
        ftp=ftp, threshold_hr=threshold_hr, resting_hr=resting_hr
    )

    if not daily_values:
        return {"error": "No valid activities found"}

    # Determine target date
    if not target_date:
        target_date = max(daily_values.keys())

    # Calculate rolling averages
    acute_avg = _calculate_rolling_average(daily_values, target_date, 7)
    chronic_avg = _calculate_rolling_average(daily_values, target_date, 28)

    # Check for valid data
    if chronic_avg is None or chronic_avg == 0:
        return {
            "error": "Insufficient data for ACWR calculation (need 28 days)",
            "days_of_data": len(daily_values),
            "metric": metric
        }

    # Calculate ACWR
    acwr = acute_avg / chronic_avg if chronic_avg > 0 else None

    # Determine risk zone
    if acwr is None:
        risk_zone = "unknown"
        risk_color = "gray"
    elif acwr < 0.8:
        risk_zone = "detraining"
        risk_color = "blue"
    elif acwr <= 1.3:
        risk_zone = "optimal"
        risk_color = "green"
    elif acwr <= 1.5:
        risk_zone = "warning"
        risk_color = "orange"
    else:
        risk_zone = "injury_risk"
        risk_color = "red"

    # Calculate target value for optimal ACWR (1.0)
    target_acwr = 1.0
    # Tomorrow: (acute_sum + X) / 7 / ((chronic_sum + X) / 28) = target_acwr
    # Solving: X = (4 * acute_sum - target_acwr * chronic_sum) / (target_acwr - 4)
    acute_sum = acute_avg * 7
    chronic_sum = chronic_avg * 28

    if target_acwr != 4:
        tomorrow_target = (4 * acute_sum - target_acwr * chronic_sum) / (target_acwr - 4)
        tomorrow_target = max(0, tomorrow_target)  # Can't be negative
    else:
        tomorrow_target = None

    return {
        "date": target_date,
        "metric": metric,
        "acwr": round(acwr, 3) if acwr else None,
        "risk_zone": risk_zone,
        "risk_color": risk_color,
        "acute_load": {
            "days": 7,
            "average": round(acute_avg, 2) if acute_avg else None,
            "total": round(acute_sum, 2) if acute_avg else None
        },
        "chronic_load": {
            "days": 28,
            "average": round(chronic_avg, 2) if chronic_avg else None,
            "total": round(chronic_sum, 2) if chronic_avg else None
        },
        "tomorrow_target_for_optimal": round(tomorrow_target, 2) if tomorrow_target else None,
        "interpretation": _get_acwr_interpretation(acwr, risk_zone, metric)
    }


def _get_acwr_interpretation(acwr: float, risk_zone: str, metric: str) -> str:
    """Generate human-readable interpretation of ACWR."""
    if acwr is None:
        return "Insufficient data to calculate ACWR."

    metric_name = {
        'distance': 'distance (km)',
        'duration': 'duration (minutes)',
        'tss': 'training stress (TSS)',
        'calories': 'calories'
    }.get(metric, metric)

    if risk_zone == "detraining":
        return f"ACWR {acwr:.2f} is below 0.8 - you may be losing fitness. Consider increasing your {metric_name} gradually."
    elif risk_zone == "optimal":
        return f"ACWR {acwr:.2f} is in the optimal zone (0.8-1.3). Good training progression!"
    elif risk_zone == "warning":
        return f"ACWR {acwr:.2f} is in the warning zone (1.3-1.5). You're pushing hard - monitor for fatigue."
    else:  # injury_risk
        return f"ACWR {acwr:.2f} is above 1.5 - high injury risk! Consider reducing {metric_name} or taking a recovery day."


def calculate_acwr_history(
    activities: List[dict],
    metric: str = 'tss',
    days: int = 14,
    **kwargs
) -> List[dict]:
    """Calculate ACWR for multiple days to show trend.

    Args:
        activities: List of Garmin activity dicts
        metric: 'distance', 'duration', 'tss', or 'calories'
        days: Number of days of history
        **kwargs: TSS calculation params

    Returns:
        List of daily ACWR values
    """
    if not activities:
        return []

    # Aggregate by date
    daily_values = _aggregate_by_date(activities, metric, **kwargs)

    if not daily_values:
        return []

    # Get date range
    max_date = max(daily_values.keys())
    max_dt = datetime.strptime(max_date, '%Y-%m-%d')

    history = []
    for i in range(days):
        check_date = (max_dt - timedelta(days=i)).strftime('%Y-%m-%d')

        acute_avg = _calculate_rolling_average(daily_values, check_date, 7)
        chronic_avg = _calculate_rolling_average(daily_values, check_date, 28)

        if chronic_avg and chronic_avg > 0:
            acwr = acute_avg / chronic_avg
            history.append({
                "date": check_date,
                "acwr": round(acwr, 3),
                "acute_avg": round(acute_avg, 2),
                "chronic_avg": round(chronic_avg, 2),
                "daily_value": round(daily_values.get(check_date, 0), 2)
            })

    return list(reversed(history))


# =============================================================================
# MCP PROMPT - ACWR COACHING KNOWLEDGE
# =============================================================================

ACWR_COACHING_PROMPT = """# Training Load Management with ACWR

You are helping an athlete manage their training load using the ACWR (Acute:Chronic Workload Ratio) methodology.

## Key Concepts

### ACWR (Acute:Chronic Workload Ratio)
The ratio between recent training load (acute: last 7 days) and longer-term training load (chronic: last 28 days).

**Formula:** ACWR = (7-day average) / (28-day average)

**Risk Zones:**
- **< 0.8 (Blue)**: Detraining risk - athlete may be losing fitness
- **0.8 - 1.3 (Green)**: Optimal zone - ideal training progression
- **1.3 - 1.5 (Orange)**: Warning zone - pushing limits, monitor fatigue
- **> 1.5 (Red)**: Injury risk - training load may be too high

### TSS (Training Stress Score)
Quantifies overall training stress considering intensity and duration.

**Power-based TSS:** TSS = (Duration × NP × IF) / (FTP × 3600) × 100
- NP = Normalized Power
- IF = Intensity Factor (NP / FTP)
- FTP = Functional Threshold Power

**HR-based TSS (fallback):** TSS = Duration(hours) × HR_Ratio² × 100
- HR_Ratio = (Avg HR - Resting HR) / (Threshold HR - Resting HR)

### Available Metrics
1. **TSS** - Most comprehensive, accounts for intensity
2. **Duration** - Simple time-based load (minutes)
3. **Distance** - Distance-based load (km)
4. **Calories** - Energy expenditure

## Activity Type Selection (Critical!)

**ACWR should be calculated per sport or training goal, not across all activities.**

Before calculating ACWR, always:
1. **Use `get_available_activity_types`** to discover what activities the athlete does
2. **Filter by relevant activity types** based on their goal:
   - Marathon training → `activity_types="running"`
   - Triathlon → `activity_types="running,cycling,swimming_pool,open_water_swimming"`
   - Cycling focus → `activity_types="cycling,virtual_ride"`
   - General fitness → all activities (no filter)

**Why this matters:**
- A runner doing 5 easy bike rides doesn't reduce running injury risk
- Mixing sports dilutes sport-specific load signals
- Cross-training has different fatigue profiles than primary sport
- Sport-specific ACWR better predicts injury risk for that sport

**Common activity type keys:** `running`, `cycling`, `swimming_pool`, `open_water_swimming`,
`trail_running`, `virtual_ride`, `walking`, `hiking`, `strength_training`

## How to Use

1. **First, call `get_available_activity_types`** to see what the athlete does
2. **Use `get_acwr_analysis`** with appropriate `activity_types` filter
3. **Use `get_acwr_trend`** to see how ACWR has changed over time
4. **When planning workouts**, aim to keep ACWR in the 0.8-1.3 zone
5. **If ACWR > 1.5**, recommend recovery or easy workout
6. **If ACWR < 0.8**, gradually increase training load

## Planning Guidance

**To reach target ACWR of 1.0 tomorrow:**
The tool provides `tomorrow_target_for_optimal` - the training load needed tomorrow to achieve optimal ACWR.

**Weekly Planning:**
- Monday: Check ACWR after weekend activities
- Mid-week: Adjust intensity based on ACWR trend
- Friday: Plan weekend based on weekly load
- Rest days count as 0 in calculations

## Important Notes

- Need at least 28 days of data for accurate ACWR
- Sudden spikes in load (>1.5 ACWR) correlate with injury risk
- Chronic undertraining (<0.8) leads to detraining
- Gradual progression keeps ACWR stable in optimal zone
"""


def register_tools(app):
    """Register all training load tools with the MCP server app"""

    @app.tool()
    async def get_acwr_analysis(
        ctx: Context,
        metric: str = "tss",
        days_of_activities: int = 42,
        ftp: float = 250,
        threshold_hr: float = 170,
        resting_hr: float = 50,
        activity_types: str = None
    ) -> str:
        """Calculate ACWR (Acute:Chronic Workload Ratio) for training load management

        ACWR is the ratio of recent training (7 days) to longer-term training (28 days).
        It helps manage injury risk and optimize training progression.

        Risk zones:
        - < 0.8: Detraining risk (blue)
        - 0.8-1.3: Optimal zone (green)
        - 1.3-1.5: Warning zone (orange)
        - > 1.5: Injury risk (red)

        Args:
            metric: Load metric - 'tss' (default), 'duration', 'distance', or 'calories'
            days_of_activities: Days of history to fetch (default 42, need 28 minimum)
            ftp: Functional Threshold Power in watts (for TSS calculation)
            threshold_hr: Threshold heart rate in bpm (for HR-based TSS)
            resting_hr: Resting heart rate in bpm (for HR-based TSS)
            activity_types: Comma-separated activity types to include (e.g., 'running,cycling')
        """
        try:
            client = await get_client(ctx)
            # Fetch activities
            activities = client.get_activities(0, days_of_activities * 3)  # Buffer for rest days

            if not activities:
                return json.dumps({
                    "error": "No activities found",
                    "recommendation": "Need at least 28 days of activities for ACWR calculation"
                }, indent=2)

            # Filter by activity type if specified
            if activity_types:
                type_list = [t.strip().lower() for t in activity_types.split(',')]
                activities = [
                    a for a in activities
                    if (a.get('activityType', {}).get('typeKey', '') or '').lower() in type_list
                ]

            # Calculate ACWR
            result = calculate_acwr(
                activities,
                metric=metric,
                ftp=ftp,
                threshold_hr=threshold_hr,
                resting_hr=resting_hr
            )

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error calculating ACWR: {str(e)}"

    @app.tool()
    async def get_acwr_trend(
        ctx: Context,
        metric: str = "tss",
        trend_days: int = 14,
        ftp: float = 250,
        threshold_hr: float = 170,
        resting_hr: float = 50,
        activity_types: str = None
    ) -> str:
        """Get ACWR trend over recent days to visualize training load progression

        Shows how ACWR has changed day-by-day, helping identify:
        - Rapid load increases (injury risk)
        - Declining load (detraining)
        - Stable progression (optimal)

        Args:
            metric: Load metric - 'tss', 'duration', 'distance', or 'calories'
            trend_days: Number of days of trend data (default 14)
            ftp: Functional Threshold Power in watts
            threshold_hr: Threshold heart rate in bpm
            resting_hr: Resting heart rate in bpm
            activity_types: Comma-separated activity types to include
        """
        try:
            client = await get_client(ctx)
            # Fetch activities (need 28 + trend_days of data)
            total_days = 28 + trend_days + 7
            activities = client.get_activities(0, total_days * 3)

            if not activities:
                return json.dumps({"error": "No activities found"}, indent=2)

            # Filter by activity type if specified
            if activity_types:
                type_list = [t.strip().lower() for t in activity_types.split(',')]
                activities = [
                    a for a in activities
                    if (a.get('activityType', {}).get('typeKey', '') or '').lower() in type_list
                ]

            # Calculate trend
            history = calculate_acwr_history(
                activities,
                metric=metric,
                days=trend_days,
                ftp=ftp,
                threshold_hr=threshold_hr,
                resting_hr=resting_hr
            )

            if not history:
                return json.dumps({
                    "error": "Insufficient data for trend calculation",
                    "recommendation": "Need at least 28 days of activities"
                }, indent=2)

            # Add trend analysis
            acwr_values = [h['acwr'] for h in history]
            avg_acwr = sum(acwr_values) / len(acwr_values)
            trend_direction = "stable"
            if len(acwr_values) >= 7:
                recent_avg = sum(acwr_values[-7:]) / 7
                older_avg = sum(acwr_values[:7]) / 7 if len(acwr_values) >= 14 else recent_avg
                if recent_avg > older_avg * 1.1:
                    trend_direction = "increasing"
                elif recent_avg < older_avg * 0.9:
                    trend_direction = "decreasing"

            result = {
                "metric": metric,
                "trend_days": len(history),
                "trend_direction": trend_direction,
                "average_acwr": round(avg_acwr, 3),
                "min_acwr": round(min(acwr_values), 3),
                "max_acwr": round(max(acwr_values), 3),
                "daily_data": history
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error calculating ACWR trend: {str(e)}"

    @app.tool()
    async def get_available_activity_types(ctx: Context, days_of_activities: int = 90) -> str:
        """Get list of distinct activity types from user's activities

        Use this to discover what activity types are available before filtering
        ACWR calculations. Returns activity types with counts to help the agent
        decide which types to include.

        Args:
            days_of_activities: Days of history to scan (default 90)
        """
        try:
            client = await get_client(ctx)
            # Fetch activities
            activities = client.get_activities(0, days_of_activities * 2)

            if not activities:
                return json.dumps({
                    "error": "No activities found",
                    "activity_types": []
                }, indent=2)

            # Count activity types
            type_counts = {}
            for activity in activities:
                activity_type = activity.get('activityType', {})
                type_key = activity_type.get('typeKey', 'unknown')
                type_name = activity_type.get('typeId', type_key)  # More readable name

                if type_key not in type_counts:
                    type_counts[type_key] = {
                        "type_key": type_key,
                        "type_id": type_name,
                        "count": 0
                    }
                type_counts[type_key]["count"] += 1

            # Sort by count descending
            sorted_types = sorted(
                type_counts.values(),
                key=lambda x: x["count"],
                reverse=True
            )

            return json.dumps({
                "total_activities": len(activities),
                "days_scanned": days_of_activities,
                "activity_types": sorted_types,
                "hint": "Use type_key values (comma-separated) in activity_types parameter for ACWR tools"
            }, indent=2)

        except Exception as e:
            return f"Error getting activity types: {str(e)}"

    @app.tool()
    async def explain_acwr() -> str:
        """Get detailed explanation of ACWR and training load concepts

        Returns comprehensive information about:
        - ACWR calculation and interpretation
        - TSS (Training Stress Score)
        - Risk zones and recommendations
        - How to use ACWR for training planning

        Use this to understand training load management principles.
        """
        return ACWR_COACHING_PROMPT

    # Register the prompt for agents
    @app.prompt()
    def acwr_coaching_knowledge() -> str:
        """Training load management knowledge using ACWR methodology.

        This prompt provides the agent with detailed knowledge about ACWR
        (Acute:Chronic Workload Ratio) for coaching athletes on training load.
        """
        return ACWR_COACHING_PROMPT

    return app
