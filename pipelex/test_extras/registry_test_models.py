from typing import ClassVar

from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.system.registries.registry_base import ModelType, RegistryModels


class FictionCharacter(StructuredContent):
    name: str
    age: int
    job: str
    backstory: str


class TestRegistryModels(RegistryModels):
    TEST_MODELS: ClassVar[list[ModelType]] = [FictionCharacter]
