from typing import ClassVar

from pipelex.system.registries.registry_base import ModelType, RegistryModels


class TemporalRegistryModels(RegistryModels):
    GENERIC: ClassVar[list[ModelType]] = []
