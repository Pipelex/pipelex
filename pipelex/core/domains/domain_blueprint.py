from pydantic import BaseModel, ConfigDict

from pipelex.core.domains.exceptions import DomainError
from pipelex.tools.misc.string_utils import is_snake_case


class DomainBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = None
    code: str
    description: str
    system_prompt: str | None = None
    system_prompt_to_structure: str | None = None
    prompt_template_to_structure: str | None = None

    @staticmethod
    def validate_domain_code(code: str) -> None:
        """Validate that a domain code follows snake_case convention."""
        if not is_snake_case(code):
            msg = f"Domain code '{code}' must be snake_case (lowercase letters, numbers, and underscores only)"
            raise DomainError(msg)
