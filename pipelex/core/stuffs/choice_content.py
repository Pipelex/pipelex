import html
import json

from pydantic import Field
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.verdict_measures import UnitInterval


class ChoiceContent(StuffContent):
    """One option picked out of a declared set"""

    choice: str = Field(description="The key of the selected option.")
    confidence: float | None = Field(
        default=None, ge=0, le=1, strict=True, description="The producer's confidence in the choice, from 0 to 1, when it reports one."
    )
    probabilities: dict[str, UnitInterval] | None = Field(
        default=None, description="The probability of each option, keyed by option key, when the producer measures a distribution."
    )

    @property
    @override
    def short_desc(self) -> str:
        return f"a choice ({self.choice})"

    @override
    def rendered_plain(self) -> str:
        return self.choice

    @override
    def rendered_html(self) -> str:
        return html.escape(self.choice)

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return self.choice

    @override
    def rendered_json(self) -> str:
        # The rendering a prompt reads: the verdict, and only the measures the producer reported.
        return json.dumps(self.model_dump(mode="json", exclude_none=True))
