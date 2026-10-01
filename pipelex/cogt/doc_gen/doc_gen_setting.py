from typing import Annotated, Union

from pydantic import BeforeValidator

from pipelex.cogt.models.model_reference import ModelReference, parse_model_reference
from pipelex.system.configuration.config_model import ConfigModel


class DocGenSetting(ConfigModel):
    """The document engine a `PipeDocGen` step prints with: a model of the `doc_gen` family, such as `reportlab-pdf`."""

    model: str
    description: str | None = None

    def desc(self) -> str:
        return f"DocGenSetting(model={self.model})"


# DocGenModelChoice accepts a DocGenSetting, a ModelReference, or a string, which is parsed into a ModelReference.
# ModelReference.model_serializer serializes it back to the string it was written as.
DocGenModelChoice = Union[
    DocGenSetting,
    Annotated[str | ModelReference, BeforeValidator(parse_model_reference)],
]
