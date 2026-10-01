from datetime import UTC, datetime


def get_current_iso_timestamp() -> str:
    """Get the current ISO timestamp."""
    return datetime.now(UTC).isoformat()
