from typing import ClassVar

from pipelex.tools.registry_models import ModelType, RegistryModels


class DeepFlowRegistryModels(RegistryModels):
    GENERIC: ClassVar[list[ModelType]] = []
