from typing import Literal

from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class VerifiedLink(StructuredContent):
    """A verified link with a verdict indicating if it should be processed or skipped."""

    source: str = Field(..., description="The source of the link")
    target: str = Field(..., description="The target of the link")
    verdict: Literal["approved", "rejected"] = Field(..., description="The verdict of the link verification")


class Constraint(StructuredContent):
    """A mathematical price constraint derived from a verified link."""

    expression: str = Field(..., description="The constraint expression, e.g. 'Price(A) <= Price(B)'")
    description: str = Field(..., description="Human-readable description of the constraint")
