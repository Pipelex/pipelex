from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

ModelType = type[BaseModel]


class RegistryModels:
    @classmethod
    def get_all_models(cls) -> list[ModelType]:
        model_lists: list[list[ModelType]] = [getattr(cls, attr) for attr in dir(cls) if isinstance(getattr(cls, attr), list)]
        all_models: set[ModelType] = set()
        for model_list in model_lists:
            all_models.update(model_list)

        return list(all_models)


class RegistryFuncs:
    @classmethod
    def get_all_functions(cls) -> list[Callable[..., Any]]:
        functions: list[Callable] = []  # pyright: ignore[reportMissingTypeArgument, reportUnknownVariableType]
        for attr in dir(cls):
            attr_value = getattr(cls, attr)
            if callable(attr_value):
                functions.append(attr_value)  # pyright: ignore[reportUnknownMemberType]
        return functions  # pyright: ignore[reportUnknownVariableType]
