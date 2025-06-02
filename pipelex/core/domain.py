from typing import Optional

from pydantic import BaseModel
from typing_extensions import Self, override

from pipelex.types import StrEnum


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
