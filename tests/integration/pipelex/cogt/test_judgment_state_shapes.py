"""Every JSON shape a PipeJudge puts in its judgment state, proven live against the judging model.

A PipeJudge sends its inputs as one JSON object keyed by input name, each value read off its content's
class: a string, a number, a boolean, an ISO date or time, an array, or a nested object without its
absent members. Nothing is flattened and nothing is stringified. These tests prove the judging model
reads each of those shapes for what it says, rather than assuming it from the vendor's schema.

Each case is a pair of states that differ only in the value under test, built by the same
`build_judgment_material` the operator calls, so the state sent is the state a run sends. The verdict
must land clearly on the yes side for one and clearly on the no side for the other: a model that
ignored or misread the shape could not flip with the value.
"""

import pytest

from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_models import JudgmentState, YesNoAnswer, YesNoQuestion
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.judgment.judgment_worker_factory import JudgmentWorkerFactory
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.kernel.judgment_ops import build_judgment_material
from pipelex.runtime_hub import get_model_deck
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import JudgmentStateShapeCase, JudgmentStateShapeCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


def _state(inputs: dict[str, StuffContent]) -> JudgmentState:
    """The state a PipeJudge declaring exactly these inputs would send, built by the operator's own material builder."""
    anything = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
    stuffs = [StuffFactory.make_stuff(concept=anything, content=content, name=name) for name, content in inputs.items()]
    memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=stuffs)
    state, images, documents = build_judgment_material(memory=memory, input_names=list(inputs))
    assert not images
    assert not documents
    return state


async def _probability_of_yes(*, judgment_combo: ModelCombo, job_metadata: JobMetadata, state: JudgmentState, question: YesNoQuestion) -> float:
    inference_model = get_model_deck().get_required_inference_model(model_handle=judgment_combo.handle, model_type=ModelType.JUDGMENT)
    worker = JudgmentWorkerFactory.make_judgment_worker(inference_model)
    job = JudgmentJobFactory.make_judgment_job(
        state=state,
        questions={"question": question},
        judgment_setting=JudgmentSetting(model=judgment_combo.handle),
        job_metadata=job_metadata,
    )
    answer = (await worker.judge(job))["question"]
    assert isinstance(answer, YesNoAnswer)
    assert answer.probability is not None
    return answer.probability


def _assert_clear_verdict(*, label: str, probability: float, expected_yes: bool) -> None:
    if expected_yes:
        assert probability >= JudgmentStateShapeCases.CLEAR_YES, f"The {label} state was not read as yes: {probability:.3f}"
    else:
        assert probability <= JudgmentStateShapeCases.CLEAR_NO, f"The {label} state was not read as no: {probability:.3f}"


@pytest.mark.judgment
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestJudgmentStateShapes:
    @pytest.mark.parametrize(("topic", "case"), JudgmentStateShapeCases.SHAPE_CASES)
    async def test_the_verdict_follows_the_value_in_each_shape(
        self,
        judgment_combo: ModelCombo,
        job_metadata: JobMetadata,
        topic: str,
        case: JudgmentStateShapeCase,
    ) -> None:
        """Both states a PipeJudge sends have the expected shape, and the verdict flips with the value inside them."""
        yes_state = _state(case.yes_inputs)
        no_state = _state(case.no_inputs)
        assert yes_state == case.expected_yes_state
        assert no_state == case.expected_no_state

        yes_probability = await _probability_of_yes(judgment_combo=judgment_combo, job_metadata=job_metadata, state=yes_state, question=case.question)
        no_probability = await _probability_of_yes(judgment_combo=judgment_combo, job_metadata=job_metadata, state=no_state, question=case.question)
        print(f"{topic}: yes side {yes_probability:.3f}, no side {no_probability:.3f}")

        _assert_clear_verdict(label="yes-side", probability=yes_probability, expected_yes=True)
        _assert_clear_verdict(label="no-side", probability=no_probability, expected_yes=False)

    @pytest.mark.parametrize(("topic", "question", "typed_state", "alternative_state", "expected_yes"), JudgmentStateShapeCases.EQUIVALENT_SHAPES)
    async def test_the_typed_shape_reads_like_its_alternative(
        self,
        judgment_combo: ModelCombo,
        job_metadata: JobMetadata,
        topic: str,
        question: YesNoQuestion,
        typed_state: JudgmentState,
        alternative_state: JudgmentState,
        expected_yes: bool,
    ) -> None:
        """The typed shape and its stringified or flattened alternative give the same clear verdict."""
        typed_probability = await _probability_of_yes(judgment_combo=judgment_combo, job_metadata=job_metadata, state=typed_state, question=question)
        alternative_probability = await _probability_of_yes(
            judgment_combo=judgment_combo, job_metadata=job_metadata, state=alternative_state, question=question
        )
        print(f"{topic}: typed {typed_probability:.3f}, alternative {alternative_probability:.3f}")

        _assert_clear_verdict(label="typed", probability=typed_probability, expected_yes=expected_yes)
        _assert_clear_verdict(label="alternative", probability=alternative_probability, expected_yes=expected_yes)
