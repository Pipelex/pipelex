import html
import json

from pydantic import Field
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.verdict_measures import UnitInterval


class RatingContent(StuffContent):
    """A position on an ordered scale of described levels"""

    # strict=True for the same reason as `YesNoContent.yes_no`: lax mode would turn "2" or 2.0 into a level.
    level: int = Field(ge=0, description="The index of the selected level, 0 being the first level declared.", strict=True)
    # Not a measure: the name the scale's declaration gives the selected level, copied from it, so a reader sees the
    # name rather than the index. The level stays the verdict a method branches on.
    label: str | None = Field(default=None, description="The label of the selected level, when the scale declares labels.")
    confidence: float | None = Field(
        default=None, ge=0, le=1, strict=True, description="The producer's confidence in the level, from 0 to 1, when it reports one."
    )
    probabilities: dict[str, UnitInterval] | None = Field(
        default=None,
        description="The probability of each level, keyed by level index written as text, when the producer measures a distribution.",
    )
    position: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        strict=True,
        description="A continuous position on the scale, from 0 to the index of the last level, when the producer measures one.",
    )

    @property
    @override
    def short_desc(self) -> str:
        return f"a rating (level {self.level})"

    def _verdict_text(self) -> str:
        """The verdict as a reader reads it: the level's label when the scale named it, its index otherwise.

        An empty label names nothing, so it falls back to the index too, rather than rendering the rating as nothing.
        """
        return self.label or str(self.level)

    @override
    def rendered_plain(self) -> str:
        return self._verdict_text()

    @override
    def rendered_html(self) -> str:
        return html.escape(self._verdict_text())

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return self._verdict_text()

    @override
    def rendered_json(self) -> str:
        # The rendering a prompt reads: the verdict, and only the measures the producer reported.
        return json.dumps(self.model_dump(mode="json", exclude_none=True))
