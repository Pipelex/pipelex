from enum import Enum
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field
from typing import Optional, List, Dict, Any, Literal


class SimpleTest(StructuredContent):
    """Generated SimpleTest class"""

    test_field: str = Field(..., description="A test field")
