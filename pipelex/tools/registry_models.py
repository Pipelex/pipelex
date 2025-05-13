# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Callable, List, Set, Type

from pydantic import BaseModel

ModelType = Type[BaseModel]


class RegistryModels:
    @classmethod
    def get_all_models(cls) -> List[ModelType]:
        model_lists: List[List[ModelType]] = [getattr(cls, attr) for attr in dir(cls) if isinstance(getattr(cls, attr), list)]
        all_models: Set[ModelType] = set()
        for model_list in model_lists:
            all_models.update(model_list)

        return list(all_models)


class RegistryFuncs:
    @classmethod
    def get_all_functions(cls) -> List[Callable[..., Any]]:
        functions: List[Callable] = []  # pyright: ignore[reportMissingTypeArgument, reportUnknownVariableType]
        for attr in dir(cls):
            attr_value = getattr(cls, attr)
            if callable(attr_value):
                functions.append(attr_value)  # pyright: ignore[reportUnknownMemberType]
        return functions  # pyright: ignore[reportUnknownVariableType]
