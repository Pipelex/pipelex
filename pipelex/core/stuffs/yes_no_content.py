import json
from typing import Any

from pydantic import Field
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent


class YesNoContent(StuffContent):
    """The answer to a yes/no question"""

    # strict=True keeps the concept a genuine boolean: pydantic's default lax mode would coerce
    # "yes"/"true"/"1"/0/1 into a bool on the dict-content path (model_validate), silently bypassing
    # the no-cross-kind-coercion contract the scalar envelope arm enforces. Only a real bool is accepted.
    yes_no: bool = Field(description="Whether the answer is yes (true) or no (false).", strict=True)
    probability: float | None = Field(
        default=None,
        ge=0,
        le=1,
        strict=True,
        description="The probability that the answer is yes, from 0 to 1, when the producer reports one.",
    )

    @property
    @override
    def short_desc(self) -> str:
        return f"a yes/no answer ({'yes' if self.yes_no else 'no'})"

    @override
    def rendered_plain(self) -> str:
        return "yes" if self.yes_no else "no"

    @override
    def rendered_html(self) -> str:
        return "yes" if self.yes_no else "no"

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return "yes" if self.yes_no else "no"

    @override
    def rendered_json(self) -> str:
        # The rendering a prompt reads: the verdict, and the probability only when one was reported.
        rendered: dict[str, Any] = {"yes_no": self.yes_no}
        if self.probability is not None:
            rendered["probability"] = self.probability
        return json.dumps(rendered)
