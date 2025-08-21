"""Invalid TOML test cases."""

from typing import List, Tuple

INVALID_TOML_SYNTAX = (
    "invalid_toml_syntax",
    """domain = "invalid_syntax"
definition = "Domain with invalid TOML syntax"

[concept]
InvalidConcept = "This is missing a closing quote""",
    None,  # Should raise an exception
)

MISSING_DOMAIN = (
    "missing_domain",
    """# Missing domain field
definition = "Domain without domain field"

[concept]
TestConcept = "A test concept"
""",
    None,  # Should raise an exception
)

# Export all error test cases
ERROR_TEST_CASES: List[Tuple[str, str]] = [
    (INVALID_TOML_SYNTAX[0], INVALID_TOML_SYNTAX[1]),
    (MISSING_DOMAIN[0], MISSING_DOMAIN[1]),
]
