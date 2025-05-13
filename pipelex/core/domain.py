# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum
from typing import Optional, Self

from pydantic import BaseModel
from typing_extensions import override


class SpecialDomain(StrEnum):
    IMPLICIT = "implicit"
    NATIVE = "native"


class Domain(BaseModel):
    code: str
    definition: str
    system_prompt: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None
    prompt_template_to_structure: Optional[str] = None

    @override
    def __str__(self):
        return self.code

    @classmethod
    def make_default(cls) -> Self:
        return cls(code=SpecialDomain.NATIVE, definition="")
