from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from pipelex.pipeline.job_metadata import JobMetadata


class ActivityReport(BaseModel):
    job_metadata: JobMetadata
    content: Any


ActivityCallback = Callable[[ActivityReport], None]
