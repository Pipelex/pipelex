# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import ClassVar, List

from pipelex.core.stuff_content import StructuredContent
from pipelex.tools.registry_models import ModelType, RegistryModels


class FictionCharacter(StructuredContent):
    name: str
    age: int
    job: str
    backstory: str


class PipelexTestModels(RegistryModels):
    TEST_MODELS: ClassVar[List[ModelType]] = [FictionCharacter]
