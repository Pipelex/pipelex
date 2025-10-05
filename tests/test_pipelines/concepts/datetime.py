from datetime import datetime

from pipelex.core.stuffs.structured_content import StructuredContent


class DateTimeEvent(StructuredContent):
    """Test model for datetime content."""

    event_name: str
    start_time: datetime
    end_time: datetime
    created_at: datetime
