from pydantic import BaseModel, ConfigDict

from pipelex.types import StrEnum


class SpecialDomain(StrEnum):
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


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    description: str | None = None
    system_prompt: str | None = None
