"""A `PipeJudge` step whose judging model's answer does not fit names the model and the verdict's concept."""

from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import JudgmentAnswerMismatchError
from pipelex.cogt.judgment.judgment_models import YesNoQuestion
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.kernel.prompt_assembly import UserPromptContent
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge, PipeJudgeQuestion
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.tools.jinja2.template_category import TemplateCategory
from tests.helpers.schema_mismatch import WORKER_MODEL, assert_names_model_and_concept, make_job_metadata


class TestPipeJudgeSchemaMismatch:
    @pytest.mark.asyncio
    async def test_the_judge_s_mismatched_answer_names_the_concept(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """The judgment worker's refusal of its own answer passes the step unwrapped; the step gives the verdict's concept."""
        load_empty_library()
        mismatch = JudgmentAnswerMismatchError("The judgment answered a question nobody asked")
        mismatch.fill_model_and_provider(WORKER_MODEL, backend_name="typesafe")
        mocker.patch("pipelex.pipe_operators.judge.pipe_judge.resolve_judgment_setting", return_value=JudgmentSetting(model="judge-deck-model"))
        mocker.patch("pipelex.pipe_operators.judge.pipe_judge.run_judgment", side_effect=mismatch)
        pipe_judge = PipeJudge(
            code="judge_urgency",
            domain_code="schema_mismatch",
            description="Judge whether the parcel is urgent",
            output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.YES_NO)),
            judgment_choice=None,
            prompt_content=UserPromptContent(template=TemplateBlueprint(template="The parcel is due today.", category=TemplateCategory.LLM_PROMPT)),
            question=PipeJudgeQuestion(judgment_question=YesNoQuestion(instructions="Is it urgent?")),
        )

        with pytest.raises(JudgmentAnswerMismatchError) as exc_info:
            await pipe_judge._live_run_operator_pipe(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
                job_metadata=make_job_metadata(),
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=PipeRunParamsFactory.make_run_params(),
            )

        assert_names_model_and_concept(failure=exc_info.value, model=WORKER_MODEL, concept="native.YesNo")
