from pipelex.mthds_parsing.exceptions import MthdsParserError

INVALID_MTHDS_SYNTAX = (
    "invalid_mthds_syntax",
    """domain = "test_domain"
description = "Domain with invalid MTHDS syntax"

[concept]
InvalidConcept = "This is missing a closing quote""",
    MthdsParserError,
)

MALFORMED_SECTION = (
    "malformed_section",
    """domain = "test_domain"
description = "Domain with malformed section"

[concept
TestConcept = "Missing closing bracket"
""",
    MthdsParserError,
)

UNCLOSED_STRING = (
    "unclosed_string",
    """domain = "test_domain"
description = "Domain with unclosed string
""",
    MthdsParserError,
)

DUPLICATE_KEYS = (
    "duplicate_keys",
    """domain = "test_domain"
description = "First definition"
description = "Duplicate definition key"

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
)

INVALID_ESCAPE_SEQUENCE = (
    "invalid_escape_sequence",
    """domain = "test_domain"
description = "Domain with invalid escape sequence \\z"

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
)

# PipelexBundleBlueprint Structure Errors
MISSING_DOMAIN = (
    "missing_domain",
    """# Missing required domain field
description = "Domain without domain field"

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
)

INVALID_DOMAIN_NAME = (
    "invalid_domain_name",
    """domain = "invalid-domain-with-hyphens"
description = "Domain with invalid characters"

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
)

EMPTY_DOMAIN = (
    "empty_domain",
    """domain = ""
description = "Domain with empty string"

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
)

INVALID_ROOT_KEY = (
    "invalid_root_key",
    """domain = "test_domain"
description = "Domain with invalid root key"
invalid_root_key = "This key should not be allowed at root level"

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
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
    MthdsParserError,
)

WRONG_TYPE_FOR_DOMAIN = (
    "wrong_type_for_domain",
    """domain = 123
description = "Domain should be string, not number"

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
)

WRONG_TYPE_FOR_DEFINITION = (
    "wrong_type_for_definition",
    """domain = "test_domain"
description = 456

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
)

WRONG_TYPE_FOR_CONCEPT_SECTION = (
    "wrong_type_for_concept_section",
    """domain = "test_domain"
description = "Domain with wrong type for concept"
concept = "should_be_dict_not_string"
""",
    MthdsParserError,
)

WRONG_TYPE_FOR_PIPE_SECTION = (
    "wrong_type_for_pipe_section",
    """domain = "test_domain"
description = "Domain with wrong type for pipe"
pipe = "should_be_dict_not_string"
""",
    MthdsParserError,
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
    MthdsParserError,
)

INVALID_TABLE_SYNTAX = (
    "invalid_table_syntax",
    """domain = "test_domain"
description = "Domain with invalid table syntax"

[concept.]
InvalidName = "Empty table name"
""",
    MthdsParserError,
)

INVALID_ARRAY_SYNTAX = (
    "invalid_array_syntax",
    """domain = "test_domain"
description = "Domain with invalid array syntax"

[concept]
TestConcept = ["Unclosed array"
""",
    MthdsParserError,
)
INVALID_ARRAY_SYNTAX2 = (
    "invalid_array_syntax",
    """domain = "test_domain"
description = "Domain with invalid array syntax"

[concept]
[concept]
""",
    MthdsParserError,
)

DOUBLE_DOT_DOMAIN = (
    "double_dot_domain",
    """domain = "legal..contracts"
description = "Domain with double dots"

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
)

LEADING_DOT_DOMAIN = (
    "leading_dot_domain",
    """domain = ".legal"
description = "Domain with leading dot"

[concept]
TestConcept = "A test concept"
""",
    MthdsParserError,
)

# Export all error test cases
ERROR_TEST_CASES: list[tuple[str, str, type[Exception] | tuple[type[Exception], ...]]] = [
    # MTHDS Syntax Errors
    INVALID_MTHDS_SYNTAX,
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
    # Hierarchical Domain Errors
    DOUBLE_DOT_DOMAIN,
    LEADING_DOT_DOMAIN,
]
