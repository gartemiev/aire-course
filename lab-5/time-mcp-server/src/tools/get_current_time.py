"""Get_current_time tool for MCP server.
"""
from mcp.types import ToolAnnotations

from core.server import mcp, tracer
from core.utils import get_tool_config

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@mcp.tool(
    annotations=ToolAnnotations(
        title="Get_current_time",
        readOnlyHint=True,  # Set to False if tool modifies state
    ),
)
@tracer.tool(name="MCP.get_current_time")
def get_current_time(timezone: str = "UTC") -> dict:
    """Prints current time to the client.

    Args:
        timezone: Name of the timezone to use (defaults to UTC)

    Returns:
        Dictionary with information about current time including timezone, day of the week, etc.
    """
    try:
        current_time = datetime.now(tz=ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        return {
            "error": "Unknown timezone",
            "timezone": timezone,
            "hint": "Use an IANA timezone name like UTC, Europe/Athens, America/New_York",
        }

    return {
        "timezone": timezone,
        "datetime": current_time.isoformat(),
        "date": current_time.date().isoformat(),
        "time": current_time.time().isoformat(),
        "utc_offset": current_time.strftime("%z"),
        "weekday": current_time.strftime("%A"),
    }
