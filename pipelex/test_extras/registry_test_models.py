from typing import ClassVar

from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.tools.registry_models import ModelType, RegistryModels


class FictionCharacter(StructuredContent):
    name: str
    age: int
    job: str
    backstory: str


class PipelexTestModels(RegistryModels):
    TEST_MODELS: ClassVar[list[ModelType]] = [FictionCharacter]
