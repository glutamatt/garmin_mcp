"""
Device functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""
import json
import datetime

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all device tools with the MCP server app"""

    @app.tool()
    async def get_devices(ctx: Context) -> str:
        """Get all Garmin devices"""
        try:
            client = await get_client(ctx)
            devices = client.get_devices()
            if not devices:
                return "No devices found"

            curated = []
            for d in devices:
                device = {
                    "device_id": d.get("deviceId"),
                    "name": d.get("displayName") or d.get("productDisplayName"),
                    "serial": d.get("serialNumber"),
                    "software_version": d.get("softwareVersionString"),
                    "last_sync": d.get("lastSyncTime"),
                }
                curated.append({k: v for k, v in device.items() if v is not None})
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_device_last_used(ctx: Context) -> str:
        """Get last used device info"""
        try:
            client = await get_client(ctx)
            device = client.get_device_last_used()
            if not device:
                return "No device found"

            curated = {
                "device_id": device.get("userDeviceId"),
                "name": device.get("lastUsedDeviceName"),
                "user_profile_id": device.get("userProfileNumber"),
            }
            upload_time = device.get("lastUsedDeviceUploadTime")
            if upload_time:
                dt = datetime.datetime.fromtimestamp(upload_time / 1000.0)
                curated["last_upload"] = dt.strftime("%Y-%m-%d %H:%M:%S")

            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_device_settings(device_id: str, ctx: Context) -> str:
        """Get device settings

        Args:
            device_id: Device ID
        """
        try:
            client = await get_client(ctx)
            settings = client.get_device_settings(device_id)
            if not settings:
                return f"No settings for device {device_id}"

            curated = {
                "device_id": settings.get("deviceId"),
                "time_format": settings.get("timeFormat"),
                "date_format": settings.get("dateFormat"),
                "measurement_units": settings.get("measurementUnits"),
            }
            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_device_alarms(ctx: Context) -> str:
        """Get all device alarms"""
        try:
            client = await get_client(ctx)
            alarms = client.get_device_alarms()
            if not alarms:
                return "No alarms found"

            curated = []
            for alarm in alarms:
                minutes = alarm.get("alarmTime")
                time_str = f"{minutes // 60:02d}:{minutes % 60:02d}" if minutes else None
                curated.append({
                    "time": time_str,
                    "enabled": alarm.get("alarmMode") == "ON",
                    "days": alarm.get("alarmDays", []),
                })
            return json.dumps({"alarms": curated}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
