"""A bundle's `main_pipe` naming no pipe it defines, through the validation verdict.

The bundle's `main_pipe` is refused as `method.pipe_unresolved`, the code a package manifest's `main_pipe` naming no
pipe already takes: the item names the missing pipe, the bundle's pipes as its candidates, nearest the name first, and
the `main_pipe` declaration as its location, both on the wire and in the Markdown a host renders from the items.

Pure unit tests: the parser, the verdict translation and the renderer, with no Pipelex boot.
"""

import pytest
from mthds.protocol.problem.models import ProblemItem
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import ValidationErrorCategory
from pipelex.errors.problem import ProblemView
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
from pipelex.pipeline.validation_render import render_invalid_verdict_markdown
from pipelex.validation_error_types import PipeValidationErrorType

_SOURCE = "hello.mthds"

_MISSING_MAIN_PIPE_MTHDS = """
domain = "hello"
description = "Greet the visitor"
main_pipe = "say_goodbye"

[pipe.say_hello]
type = "PipeLLM"
description = "Say hello"
output = "Text"
prompt = "Say hello to the visitor"

[pipe.say_good_bye]
type = "PipeLLM"
description = "Say goodbye"
output = "Text"
prompt = "Say goodbye to the visitor"
"""


def _verdict(*, mthds_content: str) -> ValidateBundleError:
    """The invalid verdict of one bundle named `hello.mthds`, as the validation translates its parser's refusal."""
    with pytest.raises(ValidateBundleError) as raised, translate_to_validate_bundle_error():
        MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source=_SOURCE)
    return raised.value


def _caller_items(*, verdict: ValidateBundleError) -> list[ProblemItem]:
    problem = verdict.to_problem(view=ProblemView.CALLER)
    assert problem.code == CoreCode.METHOD_INVALID
    assert problem.errors is not None
    return problem.errors


class TestMainPipeUnresolvedVerdict:
    def test_the_parser_categorizes_the_main_pipe_as_an_unresolved_pipe(self) -> None:
        """The blueprint error names the missing pipe, the bundle's pipes and the `main_pipe` declaration, never only a message."""
        with pytest.raises(MthdsParserError) as raised:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_MISSING_MAIN_PIPE_MTHDS, mthds_source=_SOURCE)

        [blueprint_error] = raised.value.validation_errors
        assert blueprint_error.error_type == PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY
        assert blueprint_error.source == _SOURCE
        assert blueprint_error.domain_code == "hello"
        assert blueprint_error.pipe_code is None
        assert blueprint_error.field_path == "main_pipe"
        assert blueprint_error.missing_pipe_code == "say_goodbye"
        assert blueprint_error.params == {"pipe": "main_pipe", "candidates": ["hello.say_good_bye", "hello.say_hello"]}

    def test_the_verdict_item_is_method_pipe_unresolved_at_the_main_pipe_declaration(self) -> None:
        verdict = _verdict(mthds_content=_MISSING_MAIN_PIPE_MTHDS)

        [validation_item] = verdict.validation_error_items()
        assert validation_item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert validation_item.missing_pipe_code == "say_goodbye"
        [item] = _caller_items(verdict=verdict)
        assert item.code == CoreCode.METHOD_PIPE_UNRESOLVED
        assert item.detail == "Pipe 'main_pipe' names the pipe 'say_goodbye', which does not exist."
        assert item.params is not None
        assert item.params.as_wire() == {"pipe": "main_pipe", "missing": "say_goodbye", "candidates": ["hello.say_good_bye", "hello.say_hello"]}
        assert item.location is not None
        assert item.location.as_wire() == {"field": "main_pipe", "file": _SOURCE}

    def test_every_pipe_of_the_bundle_is_a_candidate_when_none_is_near_the_name(self) -> None:
        """A `main_pipe` names one of its own bundle's pipes, so a name near none of them still offers each of them."""
        far_name_content = _MISSING_MAIN_PIPE_MTHDS.replace('main_pipe = "say_goodbye"', 'main_pipe = "translate_menu"')

        [item] = _caller_items(verdict=_verdict(mthds_content=far_name_content))

        assert item.params is not None
        assert item.params.as_wire()["candidates"] == ["hello.say_good_bye", "hello.say_hello"]

    def test_the_rendered_markdown_names_the_code_the_declaration_and_the_missing_pipe(self) -> None:
        """The Markdown a host attaches to the verdict says what to fix, where the schema violation it replaces said nothing."""
        items = _caller_items(verdict=_verdict(mthds_content=_MISSING_MAIN_PIPE_MTHDS))

        markdown = render_invalid_verdict_markdown(items=items, message="unused")

        assert markdown.splitlines() == [
            "# Validation failed",
            "",
            "1. **The method names a pipe that does not exist** (`method.pipe_unresolved`)",
            "   - Field: `main_pipe`",
            f"   - File: `{_SOURCE}`",
            "   - Pipe 'main_pipe' names the pipe 'say_goodbye', which does not exist.",
        ]
