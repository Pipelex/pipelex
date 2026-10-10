from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import JudgmentRefusedError
from pipelex.cogt.judgment.judgment_models import (
    JudgmentOutcome,
    JudgmentRefusal,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.exceptions import JudgmentOutputFieldsError
from pipelex.kernel.judgment_ops import AskedQuestion, run_multi_judgment
from pipelex.kernel.judgment_results import MultiJudgmentResult
from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.kernel.prompt_assembly import UserPromptContent
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.jinja2.template_category import TemplateCategory
from tests.unit.pipelex.cogt.judgment.fake_judgment_worker import FakeJudgmentWorker, make_fake_judgment_model
from tests.unit.pipelex.kernel.test_data import DefaultedTriage, FactoryDefaultedTriage, JudgedTriage, MultiJudgmentTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestRunMultiJudgment:
    async def _run(
        self,
        mocker: MockerFixture,
        *,
        answers: dict[str, JudgmentOutcome],
        run_mode: PipeRunMode = PipeRunMode.LIVE,
        questions: dict[str, AskedQuestion] | None = None,
        worker: FakeJudgmentWorker | None = None,
        output_class: type[StructuredContent] = JudgedTriage,
    ) -> tuple[FakeJudgmentWorker, MultiJudgmentResult]:
        """Run the judgment through the content generator, which reaches the fake worker as it would reach a backend's."""
        worker = worker or FakeJudgmentWorker(make_fake_judgment_model(), answers=answers)
        mocker.patch("pipelex.cogt.content_generation.judgment_generate._make_judgment_worker", return_value=worker)
        kernel = PipelexKernel.make(storage_scope="test/scope", read_scope=None, run_mode=run_mode, user_id="judgment-ops")
        anything = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
        memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(concept=anything, content=TextContent(text=MultiJudgmentTestCases.MESSAGE), name="message")
        )
        result = await run_multi_judgment(
            memory=memory,
            prompt_content=UserPromptContent(
                template=TemplateBlueprint(template="A message from a customer: {{ message }}", category=TemplateCategory.LLM_PROMPT)
            ),
            questions=questions or MultiJudgmentTestCases.QUESTIONS,
            judgment_setting=JudgmentSetting(model="fake-judgment-handle"),
            concept=ConceptFactory.make(
                concept_code="Triage", domain_code="judge_kernel", description="A triage", structure_class_name=output_class.__name__
            ),
            output_class=output_class,
            job_metadata=kernel.make_step_metadata(pipe_code="triage_message"),
            cogt_run_params=kernel.cogt_run_params,
            templating_style=resolve_templating_style(authored=None),
            result_name="triage",
        )
        return worker, result

    async def test_it_asks_every_question_in_one_job_and_fills_the_structure(self, mocker: MockerFixture) -> None:
        worker, result = await self._run(mocker, answers=MultiJudgmentTestCases.ANSWERS)

        (job,) = worker.judged_jobs
        assert list(job.questions) == ["urgent", "team", "severity"]
        assert job.questions["urgent"].instructions == f"Is this urgent, given that it says '{MultiJudgmentTestCases.MESSAGE}'?"
        assert job.prompt.text == f"A message from a customer: {MultiJudgmentTestCases.MESSAGE}"
        expected = JudgedTriage(
            urgent=YesNoContent(yes_no=True, probability=0.9),
            team=ChoiceContent(choice="technical", confidence=0.7),
            severity=RatingContent(level=1, label="Major", confidence=0.6),
        )
        assert result.content == expected
        assert result.memory.get_stuff("triage").content == expected
        assert result.prompt == job.prompt
        assert {name: judgment.rendered_question for name, judgment in result.judgments.items()} == {
            "urgent": f"Is this urgent, given that it says '{MultiJudgmentTestCases.MESSAGE}'?",
            "team": "Which team handles it?",
            "severity": "How severe is it?",
        }
        assert {name: judgment.outcome for name, judgment in result.judgments.items()} == MultiJudgmentTestCases.ANSWERS
        assert {name: judgment.threshold_applied for name, judgment in result.judgments.items()} == {
            "urgent": True,
            "team": None,
            "severity": None,
        }

    async def test_each_question_reads_its_own_threshold(self, mocker: MockerFixture) -> None:
        questions = {
            **MultiJudgmentTestCases.QUESTIONS,
            "urgent": AskedQuestion(question=YesNoQuestion(instructions="Is this urgent?"), threshold=0.95),
        }
        _, result = await self._run(mocker, answers=MultiJudgmentTestCases.ANSWERS, questions=questions)

        assert isinstance(result.content, JudgedTriage)
        assert result.content.urgent == YesNoContent(yes_no=False, probability=0.9)

    async def test_a_refused_question_behind_an_optional_field_leaves_it_absent(self, mocker: MockerFixture) -> None:
        """The refusal is recorded beside the verdicts and logged, and no verdict is read off it."""
        warning = mocker.patch("pipelex.kernel.judgment_ops.log.warning")

        _, result = await self._run(mocker, answers={**MultiJudgmentTestCases.ANSWERS, "severity": JudgmentRefusal()})

        assert result.content == JudgedTriage(
            urgent=YesNoContent(yes_no=True, probability=0.9), team=ChoiceContent(choice="technical", confidence=0.7), severity=None
        )
        assert result.judgments["severity"].outcome == JudgmentRefusal()
        assert result.judgments["severity"].threshold_applied is None
        warning.assert_called_once()
        assert warning.call_args.kwargs["fields"] == {
            "pipe_code": "triage_message",
            "model_handle": "fake-judgment-handle",
            "judgment_question": "severity",
        }

    async def test_a_refused_question_behind_a_required_field_raises_naming_it(self, mocker: MockerFixture) -> None:
        with pytest.raises(JudgmentRefusedError) as exc_info:
            await self._run(mocker, answers={**MultiJudgmentTestCases.ANSWERS, "team": JudgmentRefusal()})

        message = str(exc_info.value)
        assert "PipeJudge 'triage_message'" in message
        assert "'fake-judgment-handle' declined to answer the question 'team'" in message
        assert "make its output field optional" in message
        assert exc_info.value.question_name == "team"
        assert exc_info.value.error_category == "content"

    @pytest.mark.parametrize("output_class", [DefaultedTriage, FactoryDefaultedTriage])
    async def test_a_refused_question_behind_a_defaulted_field_raises_rather_than_filling_the_default(
        self, mocker: MockerFixture, output_class: type[StructuredContent]
    ) -> None:
        """A default would read as a verdict nobody gave, so only a field that may hold nothing is left absent."""
        with pytest.raises(JudgmentRefusedError) as exc_info:
            await self._run(mocker, answers={**MultiJudgmentTestCases.ANSWERS, "severity": JudgmentRefusal()}, output_class=output_class)

        assert "declined to answer the question 'severity'" in str(exc_info.value)
        assert "make its output field optional with no default" in str(exc_info.value)
        assert exc_info.value.question_name == "severity"

    async def test_a_dry_run_answers_every_question(self, mocker: MockerFixture) -> None:
        worker, result = await self._run(mocker, answers={}, run_mode=PipeRunMode.DRY)

        assert not worker.was_called
        assert result.content == JudgedTriage(
            urgent=YesNoContent(yes_no=True), team=ChoiceContent(choice="billing"), severity=RatingContent(level=0, label="Minor")
        )

    async def test_a_live_threshold_without_a_probability_warns_naming_the_question(self, mocker: MockerFixture) -> None:
        warning = mocker.patch("pipelex.kernel.judgment_ops.log.warning")

        _, result = await self._run(mocker, answers={**MultiJudgmentTestCases.ANSWERS, "urgent": YesNoAnswer(yes_no=True)})

        assert result.judgments["urgent"].threshold_applied is False
        warning.assert_called_once()
        assert warning.call_args.kwargs["fields"] == {
            "pipe_code": "triage_message",
            "threshold": 0.8,
            "model_handle": "fake-judgment-handle",
            "judgment_question": "urgent",
        }

    @pytest.mark.parametrize(
        ("questions", "named"),
        [
            pytest.param(
                {name: MultiJudgmentTestCases.QUESTIONS[name] for name in ("urgent", "team")}, "'severity'", id="a_field_no_question_answers"
            ),
            pytest.param(
                {**MultiJudgmentTestCases.QUESTIONS, "notes": AskedQuestion(question=YesNoQuestion(instructions="Any notes?"))},
                "'notes'",
                id="a_question_with_no_field",
            ),
        ],
    )
    async def test_questions_that_are_not_the_output_fields_are_refused_before_any_call(
        self, mocker: MockerFixture, questions: dict[str, Any], named: str
    ) -> None:
        worker = FakeJudgmentWorker(make_fake_judgment_model(), answers=MultiJudgmentTestCases.ANSWERS)
        with pytest.raises(JudgmentOutputFieldsError) as exc_info:
            await self._run(mocker, answers=MultiJudgmentTestCases.ANSWERS, questions=questions, worker=worker)

        assert named in str(exc_info.value)
        assert JudgedTriage.__name__ in str(exc_info.value)
        assert not worker.was_called
