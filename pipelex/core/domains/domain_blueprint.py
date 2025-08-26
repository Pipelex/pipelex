from typing import Optional

from pydantic import BaseModel

from pipelex.core.domains.exceptions import DomainError
from pipelex.tools.misc.string_utils import is_snake_case


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
            raise DomainError(f"Domain code '{code}' must be snake_case (lowercase letters, numbers, and underscores only)")
