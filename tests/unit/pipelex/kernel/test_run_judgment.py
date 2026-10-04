"""A whole judgment step: the rendered question over the material, the stored verdict, and the threshold warning."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.judgment.judgment_models import (
    JudgmentAnswer,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.judgment_ops import run_judgment
from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.system.pipe_run_mode import PipeRunMode


def _memory(contents: dict[str, StuffContent]) -> WorkingMemory:
    """A memory holding each content under its name.

    The concept is `Anything` for every one, because the material is read off the content's class and
    never off its concept: that is what keeps the kernel free of the concept library.
    """
    anything = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
    stuffs = [StuffFactory.make_stuff(concept=anything, content=content, name=name) for name, content in contents.items()]
    return WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=stuffs)


class _JudgmentProbe:
    """Stands in for the content generator: records the assignment and answers what it was told to."""

    def __init__(self, answer: JudgmentAnswer) -> None:
        self.answer = answer
        self.assignments: list[JudgmentAssignment] = []

    async def make_judgment_answers(self, *, judgment_assignment: JudgmentAssignment) -> dict[str, JudgmentAnswer]:
        self.assignments.append(judgment_assignment)
        return {"question": self.answer}


@pytest.mark.asyncio(loop_scope="class")
class TestRunJudgment:
    async def _run(
        self, mocker: MockerFixture, *, answer: JudgmentAnswer, threshold: float | None, run_mode: PipeRunMode
    ) -> tuple[_JudgmentProbe, Any]:
        probe = _JudgmentProbe(answer)
        mocker.patch("pipelex.kernel.judgment_ops.get_content_generator", return_value=probe)
        kernel = PipelexKernel.make(storage_scope="test/scope", read_scope=None, run_mode=run_mode, user_id="judgment-ops")
        result = await run_judgment(
            memory=_memory({"message": TextContent(text="The roof is on fire."), "photo": ImageContent(url="pipelex-storage://s/roof.png")}),
            question=YesNoQuestion(instructions="Is this urgent: {{ message }}"),
            input_names=["message", "photo"],
            judgment_setting=JudgmentSetting(model="judgment-ops-model"),
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.YES_NO),
            job_metadata=kernel.make_step_metadata(pipe_code="is_urgent"),
            cogt_run_params=kernel.cogt_run_params,
            templating_style=resolve_templating_style(authored=None),
            threshold=threshold,
            result_name="verdict",
        )
        return probe, result

    async def test_it_sends_the_rendered_question_over_the_material_and_stores_the_verdict(self, mocker: MockerFixture) -> None:
        probe, result = await self._run(mocker, answer=YesNoAnswer(probability=0.9), threshold=0.8, run_mode=PipeRunMode.LIVE)

        (assignment,) = probe.assignments
        assert assignment.questions["question"].instructions == "Is this urgent: The roof is on fire."
        assert assignment.state == {"message": "The roof is on fire."}
        assert list(assignment.images) == ["photo"]
        assert result.rendered_question == "Is this urgent: The roof is on fire."
        assert result.content == YesNoContent(yes_no=True, probability=0.9)
        assert result.threshold_applied is True
        assert result.memory.get_stuff("verdict").content == YesNoContent(yes_no=True, probability=0.9)

    async def test_a_live_threshold_without_a_probability_warns(self, mocker: MockerFixture) -> None:
        warning = mocker.patch("pipelex.kernel.judgment_ops.log.warning")

        _, result = await self._run(mocker, answer=YesNoAnswer(yes_no=True), threshold=0.8, run_mode=PipeRunMode.LIVE)

        assert result.threshold_applied is False
        warning.assert_called_once()
        assert "is_urgent" in warning.call_args.args[0]
        assert "judgment-ops-model" in warning.call_args.args[0]

    async def test_a_dry_threshold_without_a_probability_neither_warns_nor_records(self, mocker: MockerFixture) -> None:
        warning = mocker.patch("pipelex.kernel.judgment_ops.log.warning")

        _, result = await self._run(mocker, answer=YesNoAnswer(yes_no=True), threshold=0.8, run_mode=PipeRunMode.DRY)

        assert result.threshold_applied is None
        warning.assert_not_called()

    async def test_no_threshold_without_a_probability_does_not_warn(self, mocker: MockerFixture) -> None:
        warning = mocker.patch("pipelex.kernel.judgment_ops.log.warning")

        _, result = await self._run(mocker, answer=YesNoAnswer(yes_no=True), threshold=None, run_mode=PipeRunMode.LIVE)

        assert result.threshold_applied is None
        warning.assert_not_called()
