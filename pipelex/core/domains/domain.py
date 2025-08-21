from typing import Optional

from pydantic import BaseModel
from typing_extensions import Self

from pipelex.tools.misc.string_utils import is_snake_case
from pipelex.types import StrEnum


class DomainError(Exception):
    pass


class SpecialDomain(StrEnum):
    IMPLICIT = "implicit"
    NATIVE = "native"


class DomainBlueprint(BaseModel):
    code: str
    definition: Optional[str] = None
    system_prompt: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None
    prompt_template_to_structure: Optional[str] = None

    @staticmethod
    def validate_domain_code(code: str) -> None:
        """Validate that a domain code follows snake_case convention."""
        if not is_snake_case(code):
            raise DomainError(f"Domain code must be snake_case (lowercase letters, numbers, and underscores only) for domain '{code}'")


class Domain(BaseModel):
    code: str
    definition: Optional[str] = None
    system_prompt: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None
    prompt_template_to_structure: Optional[str] = None

    @classmethod
    def make_default(cls) -> Self:
        return cls(code=SpecialDomain.NATIVE)
