from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from pipelex.system.registries.registry_base import ModelType, RegistryModels


# for testing & examples
class Person(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    age: int
    job: str


class TemporalTestModels(RegistryModels):
    TEST_MODELS: ClassVar[list[ModelType]] = [Person]
