from pipelex.core.domains.exceptions import DomainCodeError
from pipelex.tools.misc.string_utils import is_snake_case


def is_domain_code_valid(code: str) -> bool:
    return is_snake_case(code)


def validate_domain_code(code: str) -> None:
    if not is_domain_code_valid(code=code):
        msg = f"Domain code '{code}' is not a valid domain code. It should be in snake_case."
        raise DomainCodeError(msg)
