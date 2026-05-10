"""Test structures for PipeStructure integration tests."""

from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class SimpleResult(StructuredContent):
    """A small structured result for PipeStructure tests."""

    title: str = Field(..., description="The title field")
    score: int = Field(..., description="A score")
