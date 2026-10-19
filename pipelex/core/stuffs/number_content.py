import json
import math

from pydantic import Field, field_validator
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.typing.validation_exceptions import InputFreeValueError


class NumberContent(StuffContent):
    """A number"""

    number: int | float = Field(description="The number")

    @field_validator("number")
    @classmethod
    def check_finite(cls, value: float) -> int | float:
        # NaN and the infinities are not JSON numbers: serialization would turn them into null.
        if isinstance(value, float) and not math.isfinite(value):
            msg = "number must be finite, never NaN or an infinity"
            raise InputFreeValueError(msg)
        return value

    @property
    @override
    def short_desc(self) -> str:
        return f"some number ({self.number})"

    @override
    def rendered_plain(self) -> str:
        return str(self.number)

    @override
    def rendered_html(self) -> str:
        return str(self.number)

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return str(self.number)

    @override
    def rendered_json(self) -> str:
        return json.dumps({"number": self.number})
