from typing import Annotated, Union

from pydantic import BeforeValidator, Field

from pipelex.cogt.models.model_reference import ModelReference, parse_model_reference
from pipelex.system.configuration.config_model import ConfigModel


class SearchSetting(ConfigModel):
    model: str
    include_images: bool = False
    include_inline_citations: bool = True
    max_results: int | None = Field(default=None, ge=1)
    description: str | None = None

    def desc(self) -> str:
        return f"SearchSetting(model={self.model}, max_results={self.max_results})"


# SearchModelChoice accepts SearchSetting, ModelReference, or a string (which gets parsed to ModelReference)
# The BeforeValidator ensures that strings are automatically converted to ModelReference during validation
# ModelReference.model_serializer handles serialization back to the raw string value
SearchModelChoice = Union[
    SearchSetting,
    Annotated[str | ModelReference, BeforeValidator(parse_model_reference)],
]
