"""Authored `templating_style` on PipeLLM: parsing shapes, spec passthrough, factory widening.

The authored surface is a typed union — a bare string is the `tag_style` shorthand, an inline
table is the full struct — and the union never travels past parsing: the factory widens a bare
`TagStyle` into a full `TemplatingStyle` so the runtime `PipeLLM` holds `TemplatingStyle | None`.
"""

from collections.abc import Callable
from typing import Any

from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

_BASE_TABLE: dict[str, Any] = {
    "description": "templating style parsing test",
    "inputs": {"topic": "native.Text"},
    "output": "native.Text",
    "prompt": "Here is the topic:\n@topic",
}


def _make_blueprint(**overrides: Any) -> PipeLLMBlueprint:
    return PipeLLMBlueprint.model_validate({**_BASE_TABLE, **overrides})


class TestPipeLLMTemplatingStyle:
    def test_absent_is_none_at_blueprint_level(self):
        assert _make_blueprint().templating_style is None

    def test_bare_string_is_tag_style_shorthand(self):
        blueprint = _make_blueprint(templating_style="no_tag")
        assert blueprint.templating_style is TagStyle.NO_TAG

    def test_inline_table_is_full_struct(self):
        blueprint = _make_blueprint(templating_style={"tag_style": "xml", "text_format": "markdown"})
        assert blueprint.templating_style == TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.MARKDOWN)

    def test_spec_passes_through_to_blueprint(self):
        spec = PipeLLMSpec.model_validate(
            {
                "pipe_code": "templating_style_spec_case",
                "description": "templating style spec passthrough",
                "inputs": {},
                "output": "native.Text",
                "prompt": "Say hello",
                "templating_style": "square_brackets",
            }
        )
        assert spec.to_blueprint().templating_style is TagStyle.SQUARE_BRACKETS

    def test_factory_widens_bare_tag_style(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="widen_bare_tag_style",
            blueprint=_make_blueprint(templating_style="square_brackets"),
        )
        assert pipe.templating_style == TemplatingStyle(tag_style=TagStyle.SQUARE_BRACKETS, text_format=TextFormat.PLAIN)

    def test_factory_passes_full_struct_through(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="full_struct_passthrough",
            blueprint=_make_blueprint(templating_style={"tag_style": "xml", "text_format": "markdown"}),
        )
        assert pipe.templating_style == TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.MARKDOWN)

    def test_factory_keeps_absent_as_none(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="absent_stays_none",
            blueprint=_make_blueprint(),
        )
        assert pipe.templating_style is None
