import pytest
from jinja2.exceptions import TemplateSyntaxError
from mthds.protocol.problem.registry import CoreCode
from pydantic import ValidationError

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.errors.problem import ProblemView
from pipelex.tools.jinja2.exceptions import (
    TEMPLATE_NESTING_FAULT,
    Jinja2DetectVariablesError,
    Jinja2TemplateInvalidError,
    Jinja2TemplateSyntaxError,
    TemplateNestingError,
)
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_parsing import MAX_TEMPLATE_NESTING_DEPTH, check_jinja2_parsing, parse_jinja2_template
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner

# A template nested too deeply to parse, walk or compile is the template's fault, never an unexpected failure.
#
# Jinja2 parses, walks and compiles a template recursively, so deep nesting makes Python raise `RecursionError`, or
# `SyntaxError` and `IndentationError` from its compiler. Parsing refuses such a template as one that does not parse
# (`Jinja2TemplateSyntaxError`, and a `TemplateBlueprint` validation error at load), and rendering as one that cannot
# render as written (`Jinja2TemplateInvalidError`, `method.template_invalid` on a method's template).
#
# Each kind of deep nesting the sweep found, deep enough that Jinja2 or Python fails on it unbounded: parentheses and
# brackets exhaust the parser's recursion, a chain of attribute reads or filters parses but exhausts a walk or the
# compiler's recursion, and nested `{% if %}` blocks parse but pass Python's indentation limit when compiled.
DEEP_TEMPLATES: dict[str, str] = {
    "parentheses": "{{ " + "(" * 200 + "x" + ")" * 200 + " }}",
    "brackets": "{{ " + "[" * 200 + "]" * 200 + " }}",
    "attribute_reads": "{{ x" + ".a" * 3000 + " }}",
    "filters": "{{ x" + "|lower" * 3000 + " }}",
    "if_blocks": "{% if x %}" * 150 + "y" + "{% endif %}" * 150,
}


class TestTemplateNesting:
    @pytest.mark.parametrize("template_source", DEEP_TEMPLATES.values(), ids=DEEP_TEMPLATES.keys())
    def test_parsing_refuses_a_deep_template_as_a_syntax_error(self, template_source: str) -> None:
        with pytest.raises(Jinja2TemplateSyntaxError) as exc_info:
            check_jinja2_parsing(template_source=template_source)
        assert TEMPLATE_NESTING_FAULT in str(exc_info.value)
        assert template_source not in str(exc_info.value), "the refusal must not quote the template source"

    @pytest.mark.parametrize("template_source", DEEP_TEMPLATES.values(), ids=DEEP_TEMPLATES.keys())
    def test_the_bounded_parse_raises_a_template_syntax_error(self, template_source: str) -> None:
        jinja2_env = make_jinja2_env_without_loader(template_category=TemplateCategory.LLM_PROMPT)
        with pytest.raises(TemplateNestingError) as exc_info:
            parse_jinja2_template(jinja2_env=jinja2_env, template_source=template_source)
        assert isinstance(exc_info.value, TemplateSyntaxError), "every parse site already refuses a TemplateSyntaxError"

    @pytest.mark.parametrize("template_source", DEEP_TEMPLATES.values(), ids=DEEP_TEMPLATES.keys())
    def test_the_template_lints_refuse_a_deep_template_as_a_parse_failure(self, template_source: str) -> None:
        with pytest.raises(Jinja2DetectVariablesError):
            detect_jinja2_required_variables(template_category=TemplateCategory.LLM_PROMPT, template_source=template_source)

    @pytest.mark.parametrize("template_source", DEEP_TEMPLATES.values(), ids=DEEP_TEMPLATES.keys())
    def test_a_template_blueprint_refuses_a_deep_template_at_validation(self, template_source: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            TemplateBlueprint(template=template_source, category=TemplateCategory.BASIC)
        assert TEMPLATE_NESTING_FAULT in str(exc_info.value)

    @pytest.mark.builds_problems_without_required_params(reason="renders outside any pipe, whose failure location names the pipe")
    @pytest.mark.parametrize("template_source", DEEP_TEMPLATES.values(), ids=DEEP_TEMPLATES.keys())
    def test_rendering_a_deep_method_template_is_an_invalid_template(self, template_source: str) -> None:
        with pytest.raises(Jinja2TemplateInvalidError) as exc_info:
            render_jinja2_sync(
                template_source=template_source,
                template_category=TemplateCategory.BASIC,
                templating_context={"x": "value"},
                template_owner=TemplateOwner.METHOD,
            )
        error = exc_info.value
        assert error.fault == TEMPLATE_NESTING_FAULT
        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.METHOD_TEMPLATE_INVALID

    def test_a_static_nesting_python_cannot_compile_is_an_invalid_template_at_render(self) -> None:
        """Nested `{% for %}` blocks parse within the bound but pass Python's static nesting limit when compiled."""
        template_source = "{% for a in x %}" * 30 + "y" + "{% endfor %}" * 30
        check_jinja2_parsing(template_source=template_source)
        with pytest.raises(Jinja2TemplateInvalidError) as exc_info:
            render_jinja2_sync(
                template_source=template_source,
                template_category=TemplateCategory.BASIC,
                templating_context={"x": ["value"]},
                template_owner=TemplateOwner.METHOD,
            )
        assert exc_info.value.fault == TEMPLATE_NESTING_FAULT

    def test_a_template_within_the_bound_renders(self) -> None:
        depth = MAX_TEMPLATE_NESTING_DEPTH // 4
        template_source = "{% if x %}" * depth + "{{ x }}" + "{% endif %}" * depth
        check_jinja2_parsing(template_source=template_source)
        rendered = render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.BASIC,
            templating_context={"x": "value"},
            template_owner=TemplateOwner.METHOD,
        )
        assert rendered == "value"
