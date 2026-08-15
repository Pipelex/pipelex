"""Unit tests pinning that rendering an LLM prompt never mutates library-held objects.

`PipeLibrary.get_required_pipe` hands out the stored pipe instance — nothing copies it — so
any write-back performed while rendering a prompt pollutes shared, long-lived state. Two
sites used to do exactly that: `PipeLLM._live_run_operator_pipe` cached the config-derived
templating style onto `self.llm_prompt_spec`, and `LLMPromptBlueprint._unravel_text` wrote
the spec-level style into the caller's `TemplateBlueprint`.

Pinned behaviors:

- rendering a prompt leaves the `TemplateBlueprint` untouched (the run-scoped style is
  passed as a parameter, never stored)
- a template-declared `templating_style` wins over the resolved one; without one, the
  resolved style governs
- a dry run of a `PipeLLM` leaves `pipe.model_dump()` byte-identical, so the serialized form
  that feeds the graph registry and the Temporal crate payload does not depend on run order
"""

from collections.abc import Callable

import pytest

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.llm_prompt_blueprint import LLMPromptBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

_XML_STYLE = TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.PLAIN)
_NO_TAG_STYLE = TemplatingStyle(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN)

_PROMPT_TEMPLATE = "Here is the topic:\n@topic"


def _make_working_memory() -> WorkingMemory:
    return WorkingMemoryFactory.make_from_single_stuff(
        stuff=StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=TextContent(text="Bees are great"),
            name="topic",
        ),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPromptRenderingPurity:
    async def test_make_llm_prompt_does_not_mutate_the_template_blueprint(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Regression: `_unravel_text` used to write the run-scoped style into the caller's
        `TemplateBlueprint`, which on a library-held pipe is shared long-lived state.
        """
        load_empty_library()
        template_blueprint = TemplateBlueprint(template=_PROMPT_TEMPLATE, category=TemplateCategory.LLM_PROMPT)
        spec = LLMPromptBlueprint(prompt_blueprint=template_blueprint)
        spec_snapshot = spec.model_dump()

        await spec.make_llm_prompt(
            output_concept_ref="native.Text",
            context_provider=_make_working_memory(),
            templating_style=_XML_STYLE,
        )

        # The run-scoped style stayed run-scoped: nothing was written onto the blueprint...
        assert template_blueprint.templating_style is None
        # ...nor anywhere else on the spec, so its serialized form is unchanged by rendering.
        assert spec.model_dump() == spec_snapshot

    @pytest.mark.parametrize(
        ("topic", "blueprint_style", "passed_style", "expects_xml_tag"),
        [
            ("template style wins over the resolved one", _XML_STYLE, _NO_TAG_STYLE, True),
            ("resolved style governs when the template declares none", None, _XML_STYLE, True),
            ("resolved style is really applied, not merely tolerated", None, _NO_TAG_STYLE, False),
        ],
    )
    async def test_effective_style_precedence(
        self,
        load_empty_library: Callable[[], str],
        topic: str,
        blueprint_style: TemplatingStyle | None,
        passed_style: TemplatingStyle,
        expects_xml_tag: bool,
    ):
        """A template-declared style takes precedence over the resolved one.

        The XML tag style wraps an `@variable` in `<name>...</name>`; NO_TAG inlines it bare,
        so the rendered text tells us which style actually governed.
        """
        load_empty_library()
        spec = LLMPromptBlueprint(
            prompt_blueprint=TemplateBlueprint(
                template=_PROMPT_TEMPLATE,
                category=TemplateCategory.LLM_PROMPT,
                templating_style=blueprint_style,
            ),
        )

        llm_prompt = await spec.make_llm_prompt(
            output_concept_ref="native.Text",
            context_provider=_make_working_memory(),
            templating_style=passed_style,
        )

        assert llm_prompt.user_text is not None
        assert ("<topic>" in llm_prompt.user_text) is expects_xml_tag, f"wrong effective style for case: {topic}"
        # Either way the content is rendered — the style governs the wrapping, not the payload.
        assert "Bees are great" in llm_prompt.user_text

    async def test_dry_run_does_not_mutate_the_pipe(
        self,
        load_empty_library: Callable[[], str],
    ):
        """Regression: the operator used to cache the config-derived templating style onto
        `self.llm_prompt_spec`, so a pipe's `model_dump()` — which feeds the graph registry and
        the crate payload sent to a Temporal worker — differed before and after its first run.
        """
        load_empty_library()
        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="test_prompt_rendering_purity",
            blueprint=PipeLLMBlueprint(
                description="purity test pipe",
                inputs={"topic": "native.Text"},
                output="native.Text",
                prompt=_PROMPT_TEMPLATE,
            ),
        )
        snapshot = pipe_llm.model_dump()

        await pipe_llm._dry_run_operator_pipe(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            job_metadata=JobMetadata(user_id="pytest", pipeline_run_id="test_prompt_rendering_purity"),
            working_memory=_make_working_memory(),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
        )

        assert pipe_llm.model_dump() == snapshot
