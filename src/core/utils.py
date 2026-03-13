"""
Utility functions for Intune Device Healer
"""

from datetime import datetime
import re


def parse_graph_datetime(date_string: str) -> datetime:
    """
    Parse Microsoft Graph datetime strings which can have 7-digit microseconds.

    Microsoft Graph returns dates like: 2026-02-16T05:21:08.9749073+00:00
    Python's fromisoformat only supports up to 6-digit microseconds.

    Args:
        date_string: ISO format datetime string from Graph API

    Returns:
        datetime object
    """
    if not date_string:
        return None

    # Replace Z with +00:00 for timezone
    date_string = date_string.replace("Z", "+00:00")

    # Fix microseconds if they have 7 digits (trim to 6 digits)
    # Pattern: T12:34:56.1234567+00:00 -> T12:34:56.123456+00:00
    pattern = r'(\.\d{6})\d+([\+\-]\d{2}:\d{2})'
    date_string = re.sub(pattern, r'\1\2', date_string)

    try:
        return datetime.fromisoformat(date_string)
    except ValueError as e:
        # If still fails, try removing microseconds entirely
        date_string = re.sub(r'\.\d+', '', date_string)
        return datetime.fromisoformat(date_string)


def format_bytes(bytes_value: int) -> str:
    """
    Format bytes into human-readable format.

    Args:
        bytes_value: Number of bytes

    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    if bytes_value is None:
        return "Unknown"

    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def calculate_storage_percentage(total: float, free: float) -> float:
    """
    Calculate storage usage percentage.

    Args:
        total: Total storage in GB
        free: Free storage in GB

    Returns:
        Usage percentage (0-100)
    """
    if not total or total == 0:
        return 0.0

    used = total - free
    return (used / total) * 100
