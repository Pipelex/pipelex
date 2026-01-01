from pydantic import BaseModel, ConfigDict, field_validator

from pipelex.core.domains.exceptions import DomainCodeError
from pipelex.core.domains.validation import validate_domain_code
from pipelex.types import StrEnum


class SpecialDomain(StrEnum):
    NATIVE = "native"

    @classmethod
    def is_native(cls, domain_code: str) -> bool:
        try:
            enum_value = SpecialDomain(domain_code)
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

    @field_validator("code", mode="before")
    @classmethod
    def validate_domain_syntax(cls, domain_code: str) -> str:
        try:
            validate_domain_code(code=domain_code)
        except DomainCodeError as exc:
            msg = f"Error when trying to validate the pipelex bundle at domain '{domain_code}': {exc}"
            raise ValueError(msg) from exc
        return domain_code
