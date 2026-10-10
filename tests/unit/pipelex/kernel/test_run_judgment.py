"""A whole judgment step: the assembled evidence, the rendered question, the stored verdict, the refusal and the threshold warning."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.dry_mock import dry_judgment_gen_answers
from pipelex.cogt.exceptions import JudgmentRefusedError
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.judgment.judgment_models import (
    JudgmentOutcome,
    JudgmentQuestion,
    JudgmentRefusal,
    RatingAnswer,
    RatingLevel,
    RatingQuestion,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.judgment_ops import run_judgment
from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.kernel.prompt_assembly import UserPromptContent
from pipelex.kernel.prompt_references import ImageReference, ImageReferenceKind
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.jinja2.template_category import TemplateCategory

_ROOF_PHOTO = "pipelex-storage://s/roof.png"

_EVIDENCE = UserPromptContent(
    template=TemplateBlueprint(
        template="A message from a customer: {{ message }}\nThe photo they sent: $photo", category=TemplateCategory.LLM_PROMPT
    ),
    image_references=[ImageReference(variable_path="photo", kind=ImageReferenceKind.DIRECT)],
)

_SEVERITY = RatingQuestion(
    instructions="How severe is it?",
    levels=[RatingLevel(label="Cosmetic"), RatingLevel(label="Workaround available"), RatingLevel(label="Fully blocked")],
)


def _memory(contents: dict[str, StuffContent]) -> WorkingMemory:
    anything = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
    stuffs = [StuffFactory.make_stuff(concept=anything, content=content, name=name) for name, content in contents.items()]
    return WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=stuffs)


class _JudgmentProbe:
    """Stands in for the content generator: records the assignment and answers what it was told to, or as the dry leaf does."""

    def __init__(self, outcome: JudgmentOutcome | None) -> None:
        self.outcome = outcome
        self.assignments: list[JudgmentAssignment] = []

    async def make_judgment_answers(self, *, judgment_assignment: JudgmentAssignment) -> dict[str, JudgmentOutcome]:
        self.assignments.append(judgment_assignment)
        if self.outcome is None:
            return dry_judgment_gen_answers(judgment_assignment)
        return {"question": self.outcome}


@pytest.mark.asyncio(loop_scope="class")
class TestRunJudgment:
    async def _run(
        self,
        mocker: MockerFixture,
        *,
        outcome: JudgmentOutcome | None,
        threshold: float | None = None,
        run_mode: PipeRunMode = PipeRunMode.LIVE,
        question: JudgmentQuestion | None = None,
    ) -> tuple[_JudgmentProbe, Any]:
        probe = _JudgmentProbe(outcome)
        mocker.patch("pipelex.kernel.judgment_ops.get_content_generator", return_value=probe)
        kernel = PipelexKernel.make(storage_scope="test/scope", read_scope=None, run_mode=run_mode, user_id="judgment-ops")
        result = await run_judgment(
            memory=_memory({"message": TextContent(text="The roof is on fire."), "photo": ImageContent(url=_ROOF_PHOTO, mime_type="image/png")}),
            prompt_content=_EVIDENCE,
            question=question or YesNoQuestion(instructions="Is this urgent, given that it says '{{ message }}'?"),
            judgment_setting=JudgmentSetting(model="judgment-ops-model"),
            concept=ConceptFactory.make_native_concept(
                native_concept_code=NativeConceptCode.RATING if isinstance(question, RatingQuestion) else NativeConceptCode.YES_NO
            ),
            job_metadata=kernel.make_step_metadata(pipe_code="is_urgent"),
            cogt_run_params=kernel.cogt_run_params,
            templating_style=resolve_templating_style(authored=None),
            threshold=threshold,
            result_name="verdict",
        )
        return probe, result

    async def test_it_sends_the_assembled_evidence_and_the_rendered_question_and_stores_the_verdict(self, mocker: MockerFixture) -> None:
        probe, result = await self._run(mocker, outcome=YesNoAnswer(probability=0.9), threshold=0.8)

        (assignment,) = probe.assignments
        assert list(assignment.questions) == ["question"]
        assert assignment.questions["question"].instructions == "Is this urgent, given that it says 'The roof is on fire.'?"
        assert assignment.prompt.text == "A message from a customer: The roof is on fire.\nThe photo they sent: [Image 1]"
        assert assignment.prompt.images == [PromptImageUri(uri=_ROOF_PHOTO, mime_type="image/png")]
        assert assignment.prompt.documents == []
        assert result.prompt == assignment.prompt
        assert result.rendered_question == "Is this urgent, given that it says 'The roof is on fire.'?"
        assert result.content == YesNoContent(yes_no=True, probability=0.9)
        assert result.threshold_applied is True
        assert result.memory.get_stuff("verdict").content == YesNoContent(yes_no=True, probability=0.9)

    async def test_a_refusal_raises_naming_the_step_and_the_model(self, mocker: MockerFixture) -> None:
        """A single question has nowhere to leave a refused answer absent, so the step fails, as a content error."""
        with pytest.raises(JudgmentRefusedError) as exc_info:
            await self._run(mocker, outcome=JudgmentRefusal())

        message = str(exc_info.value)
        assert "PipeJudge 'is_urgent'" in message
        assert "'judgment-ops-model'" in message
        assert "reword the question" in message
        assert exc_info.value.error_category == "content"

    async def test_a_rating_carries_the_label_of_the_level_answered(self, mocker: MockerFixture) -> None:
        _, result = await self._run(mocker, outcome=RatingAnswer(level=1, confidence=0.6), question=_SEVERITY)

        assert result.content == RatingContent(level=1, label="Workaround available", confidence=0.6)

    async def test_a_dry_run_answers_the_lowest_level_with_its_declared_label(self, mocker: MockerFixture) -> None:
        _, result = await self._run(mocker, outcome=None, question=_SEVERITY, run_mode=PipeRunMode.DRY)

        assert result.content == RatingContent(level=0, label="Cosmetic")

    async def test_a_live_threshold_without_a_probability_warns(self, mocker: MockerFixture) -> None:
        warning = mocker.patch("pipelex.kernel.judgment_ops.log.warning")

        _, result = await self._run(mocker, outcome=YesNoAnswer(yes_no=True), threshold=0.8)

        assert result.threshold_applied is False
        warning.assert_called_once()
        assert warning.call_args.kwargs["fields"] == {"pipe_code": "is_urgent", "threshold": 0.8, "model_handle": "judgment-ops-model"}

    async def test_a_dry_threshold_without_a_probability_neither_warns_nor_records(self, mocker: MockerFixture) -> None:
        warning = mocker.patch("pipelex.kernel.judgment_ops.log.warning")

        _, result = await self._run(mocker, outcome=YesNoAnswer(yes_no=True), threshold=0.8, run_mode=PipeRunMode.DRY)

        assert result.threshold_applied is None
        warning.assert_not_called()

    async def test_no_threshold_without_a_probability_does_not_warn(self, mocker: MockerFixture) -> None:
        warning = mocker.patch("pipelex.kernel.judgment_ops.log.warning")

        _, result = await self._run(mocker, outcome=YesNoAnswer(yes_no=True), threshold=None)

        assert result.threshold_applied is None
        warning.assert_not_called()
