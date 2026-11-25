from pathlib import Path
from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge
from pipelex.pipe_operators.judge.pipe_judge_blueprint import JudgeQuestionBlueprint, PipeJudgeBlueprint
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.operator.pipe_judge.cases import PipeJudgeLoadCases
from tests.integration.pipelex.pipes.stored_value_prompt.cases import STORED_TEXT, STORED_TEXT_URL
from tests.integration.pipelex.pipes.stored_value_prompt.conftest import (
    RecordingContentGenerator,
    make_text_memory,
    run_pipe_dry,
    stored_pages,
    text_inputs_read_by,
)

_SUBJECT = "a scanned contract"
_BUNDLES_DIR = Path("tests/integration/pipelex/pipes/stored_value_prompt/bundles")


def _rendered_questions(*, execution_data: dict[str, Any]) -> dict[str, str]:
    """Each question as the step rendered it, keyed by its name, the single form's one question under the empty name."""
    if "questions" in execution_data:
        return {question_name: record["rendered_question"] for question_name, record in execution_data["questions"].items()}
    return {"": execution_data["rendered_question"]}


@pytest.mark.asyncio(loop_scope="class")
class TestPipeJudgeStoredTextPrompt:
    @pytest.mark.parametrize(
        ("prompt", "question", "questions", "expected_prompt", "expected_questions", "expected_nb_loads"),
        [
            pytest.param(
                "The pages:\n{{ pages.text }}",
                "Is it about {{ subject.text }}?",
                None,
                f"The pages:\n{STORED_TEXT}",
                {"": f"Is it about {_SUBJECT}?"},
                1,
                id="the_evidence_reads_a_stored_text",
            ),
            pytest.param(
                "The subject: {{ subject.text }}",
                "Is it what these pages say: {{ pages.text }}?",
                None,
                f"The subject: {_SUBJECT}",
                {"": f"Is it what these pages say: {STORED_TEXT}?"},
                1,
                id="the_question_reads_a_stored_text",
            ),
            pytest.param(
                "The subject: {{ subject.text }}",
                None,
                {
                    "is_long": JudgeQuestionBlueprint(question="Do these pages run long: {{ pages.text }}?"),
                    "is_about": JudgeQuestionBlueprint(question="Is it about {{ subject.text }}?"),
                },
                f"The subject: {_SUBJECT}",
                {"is_long": f"Do these pages run long: {STORED_TEXT}?", "is_about": f"Is it about {_SUBJECT}?"},
                1,
                id="one_of_several_questions_reads_a_stored_text",
            ),
            pytest.param(
                "The subject: {{ subject.text }}",
                "Is it about {{ subject.text }}?",
                None,
                f"The subject: {_SUBJECT}",
                {"": f"Is it about {_SUBJECT}?"},
                0,
                id="the_evidence_and_the_question_read_inline_values_only",
            ),
        ],
    )
    async def test_the_evidence_and_questions_render_a_stored_text_in_full_and_load_only_what_they_read(
        self,
        mocker: MockerFixture,
        load_test_library: Callable[[list[Path]], None],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
        prompt: str,
        question: str | None,
        questions: dict[str, JudgeQuestionBlueprint] | None,
        expected_prompt: str,
        expected_questions: dict[str, str],
        expected_nb_loads: int,
    ) -> None:
        """A stored text the evidence or a question reads is loaded once before rendering; inline reads dispatch nothing."""
        load_test_library([_BUNDLES_DIR])
        load_spy = mocker.spy(recording_content_generator, "load_stored_texts")
        execution_data_spy = mocker.spy(PipeJudge, "_register_execution_data")
        pages = stored_pages()
        inputs = text_inputs_read_by(
            templates=[prompt, question, *(question_blueprint.question for question_blueprint in (questions or {}).values())]
        )
        pipe = PipeFactory[PipeJudge].make_from_blueprint(
            domain_code="stored_value_readers",
            pipe_code="judge_the_pages",
            blueprint=PipeJudgeBlueprint(
                description="Judge pages that may live in storage",
                inputs=inputs,
                output="PagesVerdicts" if questions else NativeConceptCode.YES_NO,
                prompt=prompt,
                question=question,
                questions=questions,
                model=PipeJudgeLoadCases.JUDGMENT_MODEL,
            ),
            concept_codes_from_the_same_domain=["PagesVerdicts"],
        )
        get_pipe_library().add_new_pipe(pipe)

        await run_pipe_dry(
            pipe=pipe,
            working_memory=make_text_memory(texts={"subject": TextContent(text=_SUBJECT), "pages": pages}),
            job_metadata=scoped_job_metadata,
        )

        execution_data: dict[str, Any] = execution_data_spy.call_args.kwargs["execution_data"]
        assert execution_data["rendered_prompt"] == expected_prompt
        assert _rendered_questions(execution_data=execution_data) == expected_questions
        assert load_spy.call_count == expected_nb_loads
        if expected_nb_loads:
            assert [uri_reference.uri for uri_reference in load_spy.call_args.kwargs["uri_references"]] == [STORED_TEXT_URL]
        else:
            assert not pages.is_loaded
