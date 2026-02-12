from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent


class PgcCombinedResult(StructuredContent):
    """Combined results from parallel analysis branches."""

    tone_result: TextContent = Field(..., description="Result of tone analysis")
    length_result: TextContent = Field(..., description="Result of length analysis")


class Pg3CombinedResult(StructuredContent):
    """Combined results from 3-branch parallel analysis."""

    tone_result: TextContent = Field(..., description="Result of tone analysis")
    length_result: TextContent = Field(..., description="Result of length analysis")
    style_result: TextContent = Field(..., description="Result of style analysis")
