from typing import Annotated, Union

from pydantic import BeforeValidator

from pipelex.cogt.models.model_reference import ModelReference, parse_model_reference
from pipelex.system.configuration.config_model import ConfigModel


class JudgmentSetting(ConfigModel):
    model: str
    description: str | None = None

    def desc(self) -> str:
        return f"JudgmentSetting(model={self.model})"


# JudgmentModelChoice accepts JudgmentSetting, ModelReference, or a string (which gets parsed to
# ModelReference). The BeforeValidator ensures that strings are automatically converted to
# ModelReference during validation; ModelReference.model_serializer handles serialization back to
# the raw string value.
JudgmentModelChoice = Union[
    JudgmentSetting,
    Annotated[str | ModelReference, BeforeValidator(parse_model_reference)],
]
