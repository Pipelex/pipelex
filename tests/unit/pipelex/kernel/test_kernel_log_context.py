"""Every kernel step function binds the metadata it is handed onto the log context, for its whole body.

A program driving the kernel directly has no interpreter around it, so nothing else binds the run and
the step: without this, the lines a kernel step emits name neither. The assertion is taken from
*inside* the call — a probe standing in for the content generator records the context bound when the
function reaches it — rather than by counting the lines a run emits, because a DRY run is nearly
silent and would prove nothing either way.

The metadata comes from the façade, as a host builds it: a run-level ``PipelexKernel.make`` carrying a
``request_id``, and a per-step copy from ``make_step_metadata``. Nothing is bound before the call, so
every identifier the probe sees was bound by the function itself, and nothing is bound after it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
from pipelex.cogt.judgment.judgment_models import JudgmentAnswer, YesNoAnswer, YesNoQuestion
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.extract_ops import build_extract_job_params, run_extract
from pipelex.kernel.img_gen_ops import build_img_gen_job_params, run_img_gen
from pipelex.kernel.judgment_ops import run_judgment
from pipelex.kernel.llm_ops import generate_object_content, run_llm_object, run_llm_text
from pipelex.kernel.llm_prompt_content import LlmPromptContent
from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.kernel.search_ops import run_search
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.log.log_context import LogContext, get_log_context

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.system.job_metadata import JobMetadata

REQUEST_ID = "req-kernel-step"

#: Named but never resolved: the probe replaces the content generator, so no worker is looked up.
LLM_SETTING = LLMSetting(model="kernel-log-context-model", temperature=0.5)


class ContentGeneratorProbe:
    """Stands in for the content generator and records the log context bound when a kernel function reaches it."""

    def __init__(self) -> None:
        self.seen: list[LogContext | None] = []

    def _record(self) -> None:
        self.seen.append(get_log_context())

    async def make_llm_text(self, **kwargs: Any) -> str:  # ruff: ignore[unused-method-argument]
        self._record()
        return "generated text"

    async def make_object(self, **kwargs: Any) -> NumberContent:  # ruff: ignore[unused-method-argument]
        self._record()
        return NumberContent(number=7)

    async def make_object_list(self, **kwargs: Any) -> list[NumberContent]:  # ruff: ignore[unused-method-argument]
        self._record()
        return [NumberContent(number=7), NumberContent(number=8)]

    async def make_extract_pages(self, **kwargs: Any) -> list[Any]:  # ruff: ignore[unused-method-argument]
        self._record()
        return []

    async def make_search_sourced_answer(self, **kwargs: Any) -> SearchResultContent:  # ruff: ignore[unused-method-argument]
        self._record()
        return SearchResultContent(answer="found")

    async def make_single_image(self, **kwargs: Any) -> ImageContent:  # ruff: ignore[unused-method-argument]
        self._record()
        return ImageContent(url="https://example.com/kernel-log-context.png")

    async def make_judgment_answers(self, **kwargs: Any) -> dict[str, JudgmentAnswer]:  # ruff: ignore[unused-method-argument]
        self._record()
        return {"question": YesNoAnswer(probability=0.8)}


def _install_probe(mocker: MockerFixture, *, ops_module: str) -> ContentGeneratorProbe:
    """Replace the content generator where the kernel ops module under test reads it."""
    probe = ContentGeneratorProbe()
    mocker.patch(f"pipelex.kernel.{ops_module}.get_content_generator", return_value=probe)
    return probe


def _kernel_and_step() -> tuple[PipelexKernel, JobMetadata]:
    kernel = PipelexKernel.make(
        storage_scope="test/scope", read_scope=None, run_mode=PipeRunMode.DRY, user_id="kernel-log-context", request_id=REQUEST_ID
    )
    return kernel, kernel.make_step_metadata()


def _assert_the_step_was_bound(*, probe: ContentGeneratorProbe, step: JobMetadata) -> None:
    assert step.pipe_run_id is not None
    assert probe.seen == [
        LogContext(request_id=REQUEST_ID, pipeline_run_id=step.run_metadata.pipeline_run_id, pipe_run_id=step.pipe_run_id),
    ], "a kernel step function must bind the metadata it is handed — the run's two identifiers and the step's own"
    assert get_log_context() is None, "the binding must be released when the step returns"


@pytest.mark.asyncio(loop_scope="class")
class TestKernelLogContext:
    async def test_run_llm_text_binds_its_step(self, mocker: MockerFixture) -> None:
        probe = _install_probe(mocker, ops_module="llm_ops")
        kernel, step = _kernel_and_step()

        await run_llm_text(
            memory=WorkingMemoryFactory.make_empty(),
            prompt_content=LlmPromptContent.make_from_text(user="Say something."),
            llm_setting=LLM_SETTING,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            output_class=TextContent,
            job_metadata=step,
            cogt_run_params=kernel.cogt_run_params,
            templating_style=resolve_templating_style(authored=None),
            result_name="reply",
        )

        _assert_the_step_was_bound(probe=probe, step=step)

    async def test_run_llm_object_binds_its_step(self, mocker: MockerFixture) -> None:
        probe = _install_probe(mocker, ops_module="llm_ops")
        kernel, step = _kernel_and_step()

        await run_llm_object(
            memory=WorkingMemoryFactory.make_empty(),
            prompt_content=LlmPromptContent.make_from_text(user="Pick a number."),
            llm_setting=LLM_SETTING,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.NUMBER),
            output_class=NumberContent,
            job_metadata=step,
            cogt_run_params=kernel.cogt_run_params,
            templating_style=resolve_templating_style(authored=None),
            result_name="answer",
        )

        _assert_the_step_was_bound(probe=probe, step=step)

    @pytest.mark.parametrize("is_multiple_output", [False, True])
    async def test_generate_object_content_binds_its_step(self, mocker: MockerFixture, is_multiple_output: bool) -> None:
        """A documented entry point of its own, which `PipeStructure` calls directly, so it binds too."""
        probe = _install_probe(mocker, ops_module="llm_ops")
        kernel, step = _kernel_and_step()

        await generate_object_content(
            job_metadata=step,
            cogt_run_params=kernel.cogt_run_params,
            llm_prompt=LLMPrompt(user_text="Pick a number."),
            llm_setting=LLM_SETTING,
            output_class=NumberContent,
            is_multiple_output=is_multiple_output,
        )

        _assert_the_step_was_bound(probe=probe, step=step)

    async def test_run_extract_binds_its_step(self, mocker: MockerFixture) -> None:
        probe = _install_probe(mocker, ops_module="extract_ops")
        kernel, step = _kernel_and_step()
        extract_setting = ExtractSetting(model="kernel-log-context-extract-model")

        await run_extract(
            memory=WorkingMemoryFactory.make_empty(),
            extract_input=ExtractInput(document_uri="https://example.com/kernel-log-context.pdf"),
            extract_setting=extract_setting,
            extract_job_params=build_extract_job_params(extract_setting=extract_setting),
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
            job_metadata=step,
            cogt_run_params=kernel.cogt_run_params,
            result_name="pages",
        )

        _assert_the_step_was_bound(probe=probe, step=step)

    async def test_run_search_binds_its_step(self, mocker: MockerFixture) -> None:
        probe = _install_probe(mocker, ops_module="search_ops")
        kernel, step = _kernel_and_step()

        await run_search(
            memory=WorkingMemoryFactory.make_empty(),
            template="What binds the log context?",
            category=TemplateCategory.LLM_PROMPT,
            search_setting=SearchSetting(model="kernel-log-context-search-model"),
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            job_metadata=step,
            cogt_run_params=kernel.cogt_run_params,
            templating_style=resolve_templating_style(authored=None),
            result_name="findings",
        )

        _assert_the_step_was_bound(probe=probe, step=step)

    async def test_run_judgment_binds_its_step(self, mocker: MockerFixture) -> None:
        probe = _install_probe(mocker, ops_module="judgment_ops")
        kernel, step = _kernel_and_step()

        await run_judgment(
            memory=WorkingMemoryFactory.make_empty(),
            question=YesNoQuestion(instructions="Does the log context bind?"),
            input_names=[],
            judgment_setting=JudgmentSetting(model="kernel-log-context-judgment-model"),
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.YES_NO),
            job_metadata=step,
            cogt_run_params=kernel.cogt_run_params,
            templating_style=resolve_templating_style(authored=None),
            result_name="verdict",
        )

        _assert_the_step_was_bound(probe=probe, step=step)

    async def test_run_img_gen_binds_its_step(self, mocker: MockerFixture) -> None:
        probe = _install_probe(mocker, ops_module="img_gen_ops")
        kernel, step = _kernel_and_step()
        img_gen_setting = ImgGenSetting(model="kernel-log-context-img-gen-model")

        await run_img_gen(
            memory=WorkingMemoryFactory.make_empty(),
            img_gen_prompt=ImgGenPrompt(positive_text="Draw the log context."),
            img_gen_setting=img_gen_setting,
            img_gen_job_params=build_img_gen_job_params(img_gen_setting=img_gen_setting),
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            output_class=ImageContent,
            job_metadata=step,
            cogt_run_params=kernel.cogt_run_params,
            result_name="picture",
        )

        _assert_the_step_was_bound(probe=probe, step=step)
