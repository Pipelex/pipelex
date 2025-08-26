from typing import Optional

from pydantic import BaseModel
from typing_extensions import Self

from pipelex.types import StrEnum


class SpecialDomain(StrEnum):
    IMPLICIT = "implicit"
    NATIVE = "native"


class Domain(BaseModel):
    code: str
    definition: Optional[str] = None
    system_prompt: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None
    prompt_template_to_structure: Optional[str] = None

    @classmethod
    def make_default(cls) -> Self:
        return cls(code=SpecialDomain.NATIVE)
