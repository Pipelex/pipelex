from typing import ClassVar

from pipelex.system.registries.registry_base import ModelType, RegistryModels


class DeepFlowRegistryModels(RegistryModels):
    GENERIC: ClassVar[list[ModelType]] = []
