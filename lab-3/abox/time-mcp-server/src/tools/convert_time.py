"""Convert_time tool for MCP server.
"""
from datetime import datetime

from mcp.types import ToolAnnotations

from core.server import mcp
from core.utils import get_tool_config
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@mcp.tool(
    annotations=ToolAnnotations(
        title="Convert_time",
        readOnlyHint=True,  # Set to False if tool modifies state
    ),
)

def convert_time(
    datetime_value: str,
    source_timezone: str | None = None,
    target_timezone: str | None = None
) -> dict:
    """Convert a date and time from one timezone to another.

    Use IANA timezone names such as UTC, Europe/Athens, or America/New_York.
    The datetime value should use ISO format, for example 2026-05-14T18:30:00.

    Args:
        datetime_value: Date and time to convert in ISO format.
        source_timezone: Timezone of the input datetime.
        target_timezone: Timezone to convert the datetime into.

    Returns:
        Dictionary with the original and converted datetime information.
    """
    # Get tool-specific configuration from kmcp.yaml
    config = get_tool_config("convert_time")
    default_source_timezone = config.get("default_source_timezone", "UTC")
    default_target_timezone = config.get("default_target_timezone", "Europe/Bucharest")

    source_timezone = source_timezone or default_source_timezone
    target_timezone = target_timezone or default_target_timezone

    try:
        source_tz = ZoneInfo(source_timezone)
        target_tz = ZoneInfo(target_timezone)
    except ZoneInfoNotFoundError as error:
        invalid_timezone = str(error).strip("'")
        return {
            "error": "Unknown timezone",
            "timezone": invalid_timezone,
            "hint": "Use an IANA timezone name like UTC, Europe/Athens, America/New_York",
        }

    try:
        parsed_datetime = datetime.fromisoformat(datetime_value)
    except ValueError:
        return {
            "error": "Invalid datetime format",
            "datetime": datetime_value,
            "hint": "Use ISO format like 2026-05-14T18:30:00",
        }

    if parsed_datetime.tzinfo is None:
        source_datetime = parsed_datetime.replace(tzinfo=source_tz)
    else:
        source_datetime = parsed_datetime.astimezone(source_tz)

    converted_datetime = source_datetime.astimezone(target_tz)

    return {
        "source_timezone": source_timezone,
        "target_timezone": target_timezone,
        "source_datetime": source_datetime.isoformat(),
        "converted_datetime": converted_datetime.isoformat(),
        "source_utc_offset": source_datetime.strftime("%z"),
        "target_utc_offset": converted_datetime.strftime("%z"),
    }
