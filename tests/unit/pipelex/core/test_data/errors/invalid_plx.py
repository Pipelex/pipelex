from pydantic import ValidationError

from pipelex.core.domains.exceptions import DomainError
from pipelex.core.interpreter import PLXDecodeError

INVALID_PLX_SYNTAX = (
    "invalid_plx_syntax",
    """domain = "test_domain"
description = "Domain with invalid PLX syntax"

[concept]
InvalidConcept = "This is missing a closing quote""",
    PLXDecodeError,
)

MALFORMED_SECTION = (
    "malformed_section",
    """domain = "test_domain"
description = "Domain with malformed section"

[concept
TestConcept = "Missing closing bracket"
""",
    PLXDecodeError,
)

UNCLOSED_STRING = (
    "unclosed_string",
    """domain = "test_domain"
description = "Domain with unclosed string
""",
    PLXDecodeError,
)

DUPLICATE_KEYS = (
    "duplicate_keys",
    """domain = "test_domain"
description = "First definition"
description = "Duplicate definition key"

[concept]
TestConcept = "A test concept"
""",
    PLXDecodeError,
)

INVALID_ESCAPE_SEQUENCE = (
    "invalid_escape_sequence",
    """domain = "test_domain"
description = "Domain with invalid escape sequence \\z"

[concept]
TestConcept = "A test concept"
""",
    PLXDecodeError,
)

# PipelexBundleBlueprint Structure Errors
MISSING_DOMAIN = (
    "missing_domain",
    """# Missing required domain field
description = "Domain without domain field"

[concept]
TestConcept = "A test concept"
""",
    ValidationError,
)

INVALID_DOMAIN_NAME = (
    "invalid_domain_name",
    """domain = "invalid-domain-with-hyphens"
description = "Domain with invalid characters"

[concept]
TestConcept = "A test concept"
""",
    DomainError,
)

EMPTY_DOMAIN = (
    "empty_domain",
    """domain = ""
description = "Domain with empty string"

[concept]
TestConcept = "A test concept"
""",
    DomainError,
)

INVALID_ROOT_KEY = (
    "invalid_root_key",
    """domain = "test_domain"
description = "Domain with invalid root key"
invalid_root_key = "This key should not be allowed at root level"

[concept]
TestConcept = "A test concept"
""",
    ValidationError,
)

MULTIPLE_INVALID_ROOT_KEYS = (
    "multiple_invalid_root_keys",
    """domain = "test_domain"
description = "Domain with multiple invalid root keys"
invalid_key_1 = "First invalid key"
invalid_key_2 = "Second invalid key"
unknown_field = "Another unknown field"

[concept]
TestConcept = "A test concept"
""",
    ValidationError,
)

WRONG_TYPE_FOR_DOMAIN = (
    "wrong_type_for_domain",
    """domain = 123
description = "Domain should be string, not number"

[concept]
TestConcept = "A test concept"
""",
    TypeError,
)

WRONG_TYPE_FOR_DEFINITION = (
    "wrong_type_for_definition",
    """domain = "test_domain"
description = 456

[concept]
TestConcept = "A test concept"
""",
    ValidationError,
)

WRONG_TYPE_FOR_CONCEPT_SECTION = (
    "wrong_type_for_concept_section",
    """domain = "test_domain"
description = "Domain with wrong type for concept"
concept = "should_be_dict_not_string"
""",
    ValidationError,
)

WRONG_TYPE_FOR_PIPE_SECTION = (
    "wrong_type_for_pipe_section",
    """domain = "test_domain"
description = "Domain with wrong type for pipe"
pipe = "should_be_dict_not_string"
""",
    ValidationError,
)

INVALID_NESTED_SECTION = (
    "invalid_nested_section",
    """domain = "test_domain"
description = "Domain with invalid nested section"

[invalid_section]
some_key = "This section is not allowed"

[concept]
TestConcept = "A test concept"
""",
    ValidationError,
)

INVALID_TABLE_SYNTAX = (
    "invalid_table_syntax",
    """domain = "test_domain"
description = "Domain with invalid table syntax"

[concept.]
InvalidName = "Empty table name"
""",
    PLXDecodeError,
)

INVALID_ARRAY_SYNTAX = (
    "invalid_array_syntax",
    """domain = "test_domain"
description = "Domain with invalid array syntax"

[concept]
TestConcept = ["Unclosed array"
""",
    PLXDecodeError,
)
INVALID_ARRAY_SYNTAX2 = (
    "invalid_array_syntax",
    """domain = "test_domain"
description = "Domain with invalid array syntax"

[concept]
[concept]
""",
    PLXDecodeError,
)

# Export all error test cases
ERROR_TEST_CASES: list[tuple[str, str, type[Exception] | tuple[type[Exception], ...]]] = [
    # PLX Syntax Errors
    INVALID_PLX_SYNTAX,
    MALFORMED_SECTION,
    UNCLOSED_STRING,
    DUPLICATE_KEYS,
    INVALID_ESCAPE_SEQUENCE,
    INVALID_TABLE_SYNTAX,
    INVALID_ARRAY_SYNTAX,
    INVALID_ARRAY_SYNTAX2,
    # PipelexBundleBlueprint Structure Errors
    MISSING_DOMAIN,
    INVALID_DOMAIN_NAME,
    EMPTY_DOMAIN,
    INVALID_ROOT_KEY,
    MULTIPLE_INVALID_ROOT_KEYS,
    WRONG_TYPE_FOR_DOMAIN,
    WRONG_TYPE_FOR_DEFINITION,
    WRONG_TYPE_FOR_CONCEPT_SECTION,
    WRONG_TYPE_FOR_PIPE_SECTION,
    INVALID_NESTED_SECTION,
]
