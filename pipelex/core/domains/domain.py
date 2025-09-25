from typing import Self

from pydantic import BaseModel

from pipelex.types import StrEnum


class SpecialDomain(StrEnum):
    IMPLICIT = "implicit"
    NATIVE = "native"


class Domain(BaseModel):
    code: str
    definition: str | None = None
    system_prompt: str | None = None
    system_prompt_to_structure: str | None = None
    prompt_template_to_structure: str | None = None

    @classmethod
    def make_default(cls) -> Self:
        return cls(code=SpecialDomain.NATIVE)
