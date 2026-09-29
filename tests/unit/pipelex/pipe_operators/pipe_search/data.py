from typing import Any, ClassVar

from pipelex.validation_error_types import PipeValidationErrorType


class PipeSearchInputCheckTestCases:
    """Cases for the blueprint input check: every declared input is read by the prompt, and every variable it reads is declared.

    A refused case is (test_id, blueprint kwargs, expected error_type, expected variable_names); an accepted
    case is (test_id, blueprint kwargs).
    """

    REFUSED_ONE_UNREAD: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "one_unread",
        {"description": "d", "inputs": {"topic": "Text", "unused": "Text"}, "output": "SearchResult", "prompt": "Latest news on $topic"},
        PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
        ["unused"],
    )

    REFUSED_TWO_UNREAD: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "two_unread",
        {"description": "d", "inputs": {"topic": "Text", "bbb": "Text", "aaa": "Text"}, "output": "SearchResult", "prompt": "News on $topic"},
        PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
        ["aaa", "bbb"],
    )

    REFUSED_UNDECLARED: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "undeclared",
        {"description": "d", "inputs": {"topic": "Text"}, "output": "SearchResult", "prompt": "News on $topic and $other"},
        PipeValidationErrorType.MISSING_INPUT_VARIABLE,
        ["other"],
    )

    # A dotted input name alone does not supply the stuff its path is read from: the root must be declared
    REFUSED_LONE_DOTTED_INPUT: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "lone_dotted_input",
        {"description": "d", "inputs": {"company.name": "Text"}, "output": "SearchResult", "prompt": "News on $company.name"},
        PipeValidationErrorType.MISSING_INPUT_VARIABLE,
        ["company"],
    )

    REFUSED_CASES: ClassVar[list[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]]] = [
        REFUSED_ONE_UNREAD,
        REFUSED_TWO_UNREAD,
        REFUSED_UNDECLARED,
        REFUSED_LONE_DOTTED_INPUT,
    ]

    ACCEPTED_CASES: ClassVar[list[tuple[str, dict[str, Any]]]] = [
        ("no_inputs", {"description": "d", "output": "SearchResult", "prompt": "Latest AI news"}),
        ("dollar_sigil", {"description": "d", "inputs": {"topic": "Text"}, "output": "SearchResult", "prompt": "News on $topic"}),
        ("dotted_path", {"description": "d", "inputs": {"company": "Company"}, "output": "SearchResult", "prompt": "News on $company.name"}),
        (
            "jinja2_if_on_optional",
            {
                "description": "d",
                "inputs": {"topic": "Text", "region": "Text?"},
                "output": "SearchResult",
                "prompt": "News on $topic{% if region %} in {{ region }}{% endif %}",
            },
        ),
        (
            "attribute_after_filter",
            {"description": "d", "inputs": {"items": "Text[]"}, "output": "SearchResult", "prompt": "News on {{ (items|first).text }}"},
        ),
        (
            "self_referential_set",
            {"description": "d", "inputs": {"topic": "Text"}, "output": "SearchResult", "prompt": "{% set topic = topic|trim %}News on {{ topic }}"},
        ),
    ]
