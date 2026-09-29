from typing import Any, ClassVar

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.validation_error_types import PipeValidationErrorType


class PipeComposeInputTestCases:
    """Test cases for PipeCompose input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_SIMPLE_TEMPLATE: ClassVar[tuple[str, PipeComposeBlueprint]] = (
        "valid_simple_template",
        PipeComposeBlueprint(
            description="Test case: valid_simple_template",
            inputs={"name": "native.Text"},
            output="native.Text",
            template="Hello {{ name }}!",
        ),
    )

    VALID_NO_INPUTS: ClassVar[tuple[str, PipeComposeBlueprint]] = (
        "valid_no_inputs",
        PipeComposeBlueprint(
            description="Test case: valid_no_inputs",
            inputs={},
            output="native.Text",
            template="Hello World!",
        ),
    )

    VALID_TWO_INPUTS: ClassVar[tuple[str, PipeComposeBlueprint]] = (
        "valid_two_inputs",
        PipeComposeBlueprint(
            description="Test case: valid_two_inputs",
            inputs={"first_name": "native.Text", "last_name": "native.Text"},
            output="native.Text",
            template="Hello {{ first_name }} {{ last_name }}!",
        ),
    )

    VALID_WITH_TEMPLATE_BLUEPRINT: ClassVar[tuple[str, PipeComposeBlueprint]] = (
        "valid_with_template_blueprint",
        PipeComposeBlueprint(
            description="Test case: valid_with_template_blueprint",
            inputs={"content": "native.Text"},
            output="native.Text",
            template=TemplateBlueprint(
                template="# Title\n\n{{ content }}",
                category=TemplateCategory.MARKDOWN,
            ),
        ),
    )

    VALID_WITH_JINJA2_CONTROL: ClassVar[tuple[str, PipeComposeBlueprint]] = (
        "valid_with_jinja2_control",
        PipeComposeBlueprint(
            description="Test case: valid_with_jinja2_control",
            inputs={"items": "native.Text"},
            output="native.Text",
            template="{% for item in items %}{{ item }}{% endfor %}",
        ),
    )

    VALID_WITH_HTML_TEMPLATE: ClassVar[tuple[str, PipeComposeBlueprint]] = (
        "valid_with_html_template",
        PipeComposeBlueprint(
            description="Test case: valid_with_html_template",
            inputs={"title": "native.Text", "body": "native.Text"},
            output="native.Text",
            template=TemplateBlueprint(
                template="<h1>{{ title }}</h1><p>{{ body }}</p>",
                category=TemplateCategory.HTML,
            ),
        ),
    )

    VALID_COMPLEX_JINJA2: ClassVar[tuple[str, PipeComposeBlueprint]] = (
        "valid_complex_jinja2",
        PipeComposeBlueprint(
            description="Test case: valid_complex_jinja2",
            inputs={"user": "native.Text", "items": "native.Text"},
            output="native.Text",
            template="Hello {{ user }}!\n{% if items %}Items: {{ items }}{% endif %}",
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeComposeBlueprint]]] = [
        VALID_SIMPLE_TEMPLATE,
        VALID_NO_INPUTS,
        VALID_TWO_INPUTS,
        VALID_WITH_TEMPLATE_BLUEPRINT,
        VALID_WITH_JINJA2_CONTROL,
        VALID_WITH_HTML_TEMPLATE,
        VALID_COMPLEX_JINJA2,
    ]


class PipeComposeInputCheckTestCases:
    """Cases for the blueprint input check: every declared input is read, and every variable read is declared.

    A refused case is (test_id, blueprint kwargs, expected error_type, expected variable_names); an accepted
    case is (test_id, blueprint kwargs). Kwargs rather than built blueprints, since a refused one cannot be built.
    """

    REFUSED_TEMPLATE_ONE_UNREAD: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "template_one_unread",
        {"description": "d", "inputs": {"topic": "Text", "unused": "Text"}, "output": "Text", "template": "About $topic"},
        PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
        ["unused"],
    )

    REFUSED_TEMPLATE_TWO_UNREAD: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "template_two_unread",
        {"description": "d", "inputs": {"topic": "Text", "bbb": "Text", "aaa": "Text"}, "output": "Text", "template": "About $topic"},
        PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
        ["aaa", "bbb"],
    )

    REFUSED_TEMPLATE_BLUEPRINT_UNREAD: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "template_blueprint_unread",
        {
            "description": "d",
            "inputs": {"content": "Text", "unused": "Text"},
            "output": "Text",
            "template": {"template": "# Title\n\n{{ content }}", "category": "markdown"},
        },
        PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
        ["unused"],
    )

    REFUSED_TEMPLATE_UNDECLARED: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "template_undeclared",
        {"description": "d", "inputs": {"topic": "Text"}, "output": "Text", "template": "About $topic and $other"},
        PipeValidationErrorType.MISSING_INPUT_VARIABLE,
        ["other"],
    )

    REFUSED_CONSTRUCT_ONE_UNREAD: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "construct_one_unread",
        {
            "description": "d",
            "inputs": {"deal": "Deal", "unused": "Text"},
            "output": "Summary",
            "construct": {"customer_name": {"from": "deal.customer_name"}, "label": {"template": "Deal $deal.amount"}},
        },
        PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
        ["unused"],
    )

    REFUSED_CONSTRUCT_TWO_UNREAD: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "construct_two_unread",
        {
            "description": "d",
            "inputs": {"deal": "Deal", "bbb": "Text", "aaa": "Text"},
            "output": "Summary",
            "construct": {"customer_name": {"from": "deal.customer_name"}},
        },
        PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
        ["aaa", "bbb"],
    )

    REFUSED_CONSTRUCT_UNDECLARED_FROM: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "construct_undeclared_from",
        {
            "description": "d",
            "inputs": {"deal": "Deal"},
            "output": "Summary",
            "construct": {"customer_name": {"from": "deal.customer_name"}, "owner": {"from": "other.name"}},
        },
        PipeValidationErrorType.MISSING_INPUT_VARIABLE,
        ["other"],
    )

    REFUSED_CONSTRUCT_UNDECLARED_NESTED_TEMPLATE: ClassVar[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]] = (
        "construct_undeclared_nested_template",
        {
            "description": "d",
            "inputs": {"deal": "Deal"},
            "output": "Summary",
            "construct": {"customer_name": {"from": "deal.customer_name"}, "address": {"line": {"template": "$place.city"}}},
        },
        PipeValidationErrorType.MISSING_INPUT_VARIABLE,
        ["place"],
    )

    REFUSED_CASES: ClassVar[list[tuple[str, dict[str, Any], PipeValidationErrorType, list[str]]]] = [
        REFUSED_TEMPLATE_ONE_UNREAD,
        REFUSED_TEMPLATE_TWO_UNREAD,
        REFUSED_TEMPLATE_BLUEPRINT_UNREAD,
        REFUSED_TEMPLATE_UNDECLARED,
        REFUSED_CONSTRUCT_ONE_UNREAD,
        REFUSED_CONSTRUCT_TWO_UNREAD,
        REFUSED_CONSTRUCT_UNDECLARED_FROM,
        REFUSED_CONSTRUCT_UNDECLARED_NESTED_TEMPLATE,
    ]

    ACCEPTED_CASES: ClassVar[list[tuple[str, dict[str, Any]]]] = [
        ("dollar_sigil", {"description": "d", "inputs": {"name": "Text"}, "output": "Text", "template": "Hello $name!"}),
        ("at_block", {"description": "d", "inputs": {"name": "Text"}, "output": "Text", "template": "Hello:\n@name\n"}),
        ("guarded_at_block_on_optional", {"description": "d", "inputs": {"note": "Text?"}, "output": "Text", "template": "Notes:\n@?note\n"}),
        (
            "jinja2_if",
            {"description": "d", "inputs": {"note": "Text?"}, "output": "Text", "template": "{% if note %}{{ note }}{% else %}none{% endif %}"},
        ),
        ("jinja2_if_only", {"description": "d", "inputs": {"flag": "Text?"}, "output": "Text", "template": "{% if flag %}flagged{% endif %}"}),
        ("dotted_path", {"description": "d", "inputs": {"deal": "Deal"}, "output": "Text", "template": "Worth $deal.amount"}),
        (
            "for_loop",
            {"description": "d", "inputs": {"items": "Text[]"}, "output": "Text", "template": "{% for item in items %}{{ item }}{% endfor %}"},
        ),
        (
            "construct_from_path",
            {"description": "d", "inputs": {"deal": "Deal"}, "output": "Summary", "construct": {"name": {"from": "deal.customer_name"}}},
        ),
        (
            "construct_nested_template",
            {
                "description": "d",
                "inputs": {"hq": "Office"},
                "output": "Summary",
                "construct": {"headquarters": {"country": "France", "phone": {"template": "+$hq.country_code $hq.phone"}}},
            },
        ),
        (
            "construct_dotted_input_name",
            {
                "description": "d",
                "inputs": {"page": "Page", "page.page_view": "Image"},
                "output": "Summary",
                "construct": {"view": {"from": "page.page_view"}, "text": {"from": "page.text_and_images"}},
            },
        ),
    ]
