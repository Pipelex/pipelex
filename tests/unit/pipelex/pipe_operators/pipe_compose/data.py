from typing import ClassVar

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError


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

    # Error test cases: (test_id, blueprint, expected_error_type, expected_error_message_fragment)
    ERROR_MISSING_INPUT_IN_TEMPLATE: ClassVar[tuple[str, PipeComposeBlueprint, type[Exception], str]] = (
        "missing_input_in_template",
        PipeComposeBlueprint(
            description="Test case: missing_input_in_template",
            inputs={},
            output="native.Text",
            template="Hello {{ name }}!",
        ),
        Exception,  # Will be PipeDefinitionError
        "Required variable 'name' is not in the inputs",
    )

    ERROR_TWO_INPUTS_THREE_VARIABLES: ClassVar[tuple[str, PipeComposeBlueprint, type[Exception], str]] = (
        "two_inputs_three_variables",
        PipeComposeBlueprint(
            description="Test case: two_inputs_three_variables",
            inputs={"first_name": "native.Text", "last_name": "native.Text"},
            output="native.Text",
            template="Hello {{ first_name }} {{ last_name }} from {{ city }}!",
        ),
        Exception,  # Will be PipeDefinitionError
        "Required variable 'city' is not in the inputs",
    )

    ERROR_INVALID_JINJA2_SYNTAX: ClassVar[tuple[str, PipeComposeBlueprint, type[Exception], str]] = (
        "invalid_jinja2_syntax",
        PipeComposeBlueprint(
            description="Test case: invalid_jinja2_syntax",
            inputs={"name": "native.Text"},
            output="native.Text",
            template="Hello {{ name }!",
        ),
        Jinja2TemplateSyntaxError,
        "Could not parse Jinja2 template",
    )

    ERROR_CASES: ClassVar[list[tuple[str, PipeComposeBlueprint, type[Exception], str]]] = [
        ERROR_MISSING_INPUT_IN_TEMPLATE,
        ERROR_TWO_INPUTS_THREE_VARIABLES,
        ERROR_INVALID_JINJA2_SYNTAX,
    ]
