from pydantic import BaseModel

from pipelex.types import Self, StrEnum


class SpecialDomain(StrEnum):
    IMPLICIT = "implicit"
    NATIVE = "native"

    @classmethod
    def is_native(cls, domain: str) -> bool:
        try:
            enum_value = SpecialDomain(domain)
        except ValueError:
            return False

        match enum_value:
            case SpecialDomain.NATIVE:
                return True
            case SpecialDomain.IMPLICIT:
                return False


class Domain(BaseModel):
    code: str
    description: str | None = None
    system_prompt: str | None = None
    system_prompt_to_structure: str | None = None
    prompt_template_to_structure: str | None = None

    @classmethod
    def make_default(cls) -> Self:
        return cls(code=SpecialDomain.NATIVE)
