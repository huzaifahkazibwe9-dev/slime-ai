"""Strict capture provenance helpers shared by screenshot pipelines."""
import re
from datetime import datetime, timedelta, timezone


def parse_exif_capture_time(exif):
    """Return an aware ISO timestamp only when EXIF supplies a UTC offset.

    EXIF DateTimeOriginal without OffsetTimeOriginal is a local wall-clock
    value, not an absolute timestamp, so it is deliberately rejected.
    """
    raw = exif.get(36867) or exif.get(306)
    offset = exif.get(36881)  # OffsetTimeOriginal
    if not isinstance(raw, str) or not isinstance(offset, str):
        return None
    try:
        captured = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
        match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", offset.strip())
        if not match:
            return None
        hours, minutes = int(match.group(2)), int(match.group(3))
        if hours > 14 or minutes > 59 or (hours == 14 and minutes != 0):
            return None
        delta = timedelta(hours=hours, minutes=minutes)
        if match.group(1) == "-":
            delta = -delta
        return captured.replace(tzinfo=timezone(delta)).isoformat()
    except (ValueError, TypeError):
        return None


def validate_capture_session_id(value):
    """Accept an explicit, bounded session token; never invent one."""
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value
    ):
        raise ValueError("Invalid capture session ID")
    return value
