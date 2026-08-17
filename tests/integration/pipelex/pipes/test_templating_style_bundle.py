"""End-to-end: a bundle authoring `templating_style` parses, loads, and renders under that style.

Also covers the operators that have no authored style of their own: they inherit the same runtime
default rather than falling into a filter-level one, which is the whole point of resolving centrally.
"""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_required_pipe
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

if TYPE_CHECKING:
    from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen

_PIPELINES_DIR = Path("tests/integration/pipelex/pipes/pipelines")


def _make_memory() -> WorkingMemory:
    return WorkingMemoryFactory.make_from_single_stuff(
        stuff=StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=TextContent(text="Bees are great"),
            name="topic",
        ),
    )


async def _render_user_text(pipe: PipeLLM) -> str:
    llm_prompt = await pipe.llm_prompt_spec.make_llm_prompt(
        output_concept_ref="native.Text",
        context_provider=_make_memory(),
        templating_style=resolve_templating_style(authored=pipe.templating_style),
    )
    assert llm_prompt.user_text is not None
    return llm_prompt.user_text


@pytest.mark.asyncio(loop_scope="class")
class TestTemplatingStyleBundle:
    async def test_bare_string_style_parses_and_governs_rendering(self, load_test_library: Callable[[list[Path]], None]):
        load_test_library([_PIPELINES_DIR])
        pipe = cast("PipeLLM", get_required_pipe("test_templating_style.square_brackets_note"))
        assert pipe.templating_style == TemplatingStyle(tag_style=TagStyle.SQUARE_BRACKETS, text_format=TextFormat.PLAIN)
        user_text = await _render_user_text(pipe)
        assert "[topic]" in user_text
        assert "[/topic]" in user_text
        assert "Bees are great" in user_text

    async def test_full_struct_style_parses_and_governs_rendering(self, load_test_library: Callable[[list[Path]], None]):
        load_test_library([_PIPELINES_DIR])
        pipe = cast("PipeLLM", get_required_pipe("test_templating_style.full_struct_note"))
        assert pipe.templating_style == TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.MARKDOWN)
        user_text = await _render_user_text(pipe)
        assert "<topic>" in user_text
        assert "</topic>" in user_text

    async def test_absent_style_renders_under_config_default(self, load_test_library: Callable[[list[Path]], None]):
        load_test_library([_PIPELINES_DIR])
        pipe = cast("PipeLLM", get_required_pipe("test_templating_style.default_style_note"))
        assert pipe.templating_style is None
        user_text = await _render_user_text(pipe)
        assert "<topic>" in user_text
        assert "</topic>" in user_text
        assert "```" not in user_text

    async def test_img_gen_prompt_renders_under_config_default(self, load_test_library: Callable[[list[Path]], None]):
        """An image prompt has no authored style, and used to render under the filters' triple-backtick
        fallback. It now inherits the same default an LLM pipe that declares nothing gets.
        """
        load_test_library([_PIPELINES_DIR])
        pipe = cast("PipeImgGen", get_required_pipe("test_templating_style.default_style_picture"))
        img_gen_prompt = await pipe.img_gen_prompt_blueprint.make_img_gen_prompt(
            context_provider=_make_memory(),
            templating_style=resolve_templating_style(authored=None),
        )
        assert "<topic>" in img_gen_prompt.positive_text
        assert "</topic>" in img_gen_prompt.positive_text
        assert "```" not in img_gen_prompt.positive_text
