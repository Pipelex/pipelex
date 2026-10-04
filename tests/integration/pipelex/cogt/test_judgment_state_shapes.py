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

import datetime
from dataclasses import dataclass
from typing import Any

import pytest

from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_models import JudgmentState, YesNoAnswer, YesNoQuestion
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.judgment.judgment_worker_factory import JudgmentWorkerFactory
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.judgment_ops import build_judgment_material
from pipelex.runtime_hub import get_model_deck
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.fixtures.model_combo import ModelCombo

# A verdict must clear the middle by this much on its side: a shape the model half-read would hover near 0.5.
CLEAR_YES = 0.8
CLEAR_NO = 0.2


class _Charge(StructuredContent):
    amount_usd: float
    status: str


class _Order(StructuredContent):
    order_id: str
    charges: list[_Charge]
    tracking_number: str | None = None


@dataclass(frozen=True)
class _ShapeCase:
    """One question over two states that differ only in the value under test, and the state the yes side must produce."""

    question: YesNoQuestion
    yes_inputs: dict[str, StuffContent]
    no_inputs: dict[str, StuffContent]
    expected_yes_state: JudgmentState


def _order(*, charges: list[_Charge], tracking_number: str | None = None) -> _Order:
    return _Order(order_id="A-104", charges=charges, tracking_number=tracking_number)


_CAPTURED = _Charge(amount_usd=49, status="captured")

SHAPE_CASES: list[Any] = [
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Does the customer ask for a refund?"),
            yes_inputs={"message": TextContent(text="I was charged twice for my order. Please refund the duplicate charge.")},
            no_inputs={"message": TextContent(text="Thanks, my parcel arrived this morning and everything is fine.")},
            expected_yes_state={"message": "I was charged twice for my order. Please refund the duplicate charge."},
        ),
        id="text_as_string",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Is the order total above 1000 USD?"),
            yes_inputs={"order_total_usd": NumberContent(number=1240)},
            no_inputs={"order_total_usd": NumberContent(number=40)},
            expected_yes_state={"order_total_usd": 1240},
        ),
        id="integer_as_number",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Is the account balance negative?"),
            yes_inputs={"balance_usd": NumberContent(number=-12.75)},
            no_inputs={"balance_usd": NumberContent(number=312.5)},
            expected_yes_state={"balance_usd": -12.75},
        ),
        id="float_as_number",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Has the refund been approved?"),
            yes_inputs={"refund_approved": YesNoContent(yes_no=True)},
            no_inputs={"refund_approved": YesNoContent(yes_no=False)},
            expected_yes_state={"refund_approved": True},
        ),
        id="yes_no_as_boolean",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Was the parcel delivered more than a week after the order was placed?"),
            yes_inputs={"ordered_on": DateContent(date=datetime.date(2026, 9, 1)), "delivered_on": DateContent(date=datetime.date(2026, 9, 20))},
            no_inputs={"ordered_on": DateContent(date=datetime.date(2026, 9, 1)), "delivered_on": DateContent(date=datetime.date(2026, 9, 3))},
            expected_yes_state={"ordered_on": "2026-09-01", "delivered_on": "2026-09-20"},
        ),
        id="dates_as_iso_strings",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Did the call take place in the middle of the night?"),
            yes_inputs={"call_time": TimeContent(time=datetime.time(3, 15))},
            no_inputs={"call_time": TimeContent(time=datetime.time(14, 30))},
            expected_yes_state={"call_time": "03:15:00"},
        ),
        id="time_as_iso_string",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Did the fraud check flag this payment?"),
            yes_inputs={"payment_checks": JSONContent(json_obj={"fraud": {"flagged": True, "score": 0.97}, "3ds": "passed"})},
            no_inputs={"payment_checks": JSONContent(json_obj={"fraud": {"flagged": False, "score": 0.02}, "3ds": "passed"})},
            expected_yes_state={"payment_checks": {"fraud": {"flagged": True, "score": 0.97}, "3ds": "passed"}},
        ),
        id="json_as_nested_object",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Was the customer charged more than once for this order?"),
            yes_inputs={"order": _order(charges=[_CAPTURED, _CAPTURED])},
            no_inputs={"order": _order(charges=[_CAPTURED])},
            expected_yes_state={
                "order": {"order_id": "A-104", "charges": [{"amount_usd": 49, "status": "captured"}, {"amount_usd": 49, "status": "captured"}]}
            },
        ),
        id="structure_as_nested_object_with_array",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Has a tracking number been assigned to the order?"),
            yes_inputs={"order": _order(charges=[_CAPTURED], tracking_number="1Z999AA10123456784")},
            no_inputs={"order": _order(charges=[_CAPTURED])},
            expected_yes_state={
                "order": {"order_id": "A-104", "charges": [{"amount_usd": 49, "status": "captured"}], "tracking_number": "1Z999AA10123456784"}
            },
        ),
        id="absent_member_left_out",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Did the customer threaten to cancel their subscription?"),
            yes_inputs={
                "messages": ListContent(items=[TextContent(text="This is the third time this happens."), TextContent(text="Fix it or I cancel.")])
            },
            no_inputs={
                "messages": ListContent(
                    items=[TextContent(text="This is the third time this happens."), TextContent(text="Thanks for the quick fix.")]
                )
            },
            expected_yes_state={"messages": ["This is the third time this happens.", "Fix it or I cancel."]},
        ),
        id="list_of_texts_as_array",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Was any of these charges refunded?"),
            yes_inputs={"charges": ListContent(items=[_CAPTURED, _Charge(amount_usd=49, status="refunded")])},
            no_inputs={"charges": ListContent(items=[_CAPTURED, _CAPTURED])},
            expected_yes_state={"charges": [{"amount_usd": 49, "status": "captured"}, {"amount_usd": 49, "status": "refunded"}]},
        ),
        id="list_of_structures_as_array_of_objects",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Was the message routed to the payments team?"),
            yes_inputs={"routing": ChoiceContent(choice="payments", confidence=0.93)},
            no_inputs={"routing": ChoiceContent(choice="shipping", confidence=0.93)},
            expected_yes_state={"routing": {"choice": "payments", "confidence": 0.93}},
        ),
        id="earlier_verdict_as_object",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Does the page ask the visitor for a password?"),
            yes_inputs={"page": HtmlContent(inner_html='<form><label>Password</label><input type="password" name="pw"></form>')},
            no_inputs={"page": HtmlContent(inner_html="<p>Our offices are closed on public holidays.</p>")},
            expected_yes_state={"page": {"inner_html": '<form><label>Password</label><input type="password" name="pw"></form>'}},
        ),
        id="html_as_wrapped_object",
    ),
    pytest.param(
        _ShapeCase(
            question=YesNoQuestion(instructions="Is the refund amount equal to the amount of one charge on the order?"),
            yes_inputs={"order": _order(charges=[_CAPTURED, _CAPTURED]), "refund_usd": NumberContent(number=49)},
            no_inputs={"order": _order(charges=[_CAPTURED, _CAPTURED]), "refund_usd": NumberContent(number=5)},
            expected_yes_state={
                "order": {"order_id": "A-104", "charges": [{"amount_usd": 49, "status": "captured"}] * 2},
                "refund_usd": 49,
            },
        ),
        id="several_inputs_related",
    ),
]


# The same fact in the typed shape a PipeJudge sends, and in the stringified or flattened shape it could have
# sent instead. Each pair must land on the same side: the typed shape loses nothing to the alternative.
EQUIVALENT_SHAPES: list[Any] = [
    pytest.param(
        YesNoQuestion(instructions="Has the refund been approved?"),
        {"refund_approved": True},
        {"refund_approved": "yes"},
        True,
        id="boolean_true_vs_word",
    ),
    pytest.param(
        YesNoQuestion(instructions="Has the refund been approved?"),
        {"refund_approved": False},
        {"refund_approved": "no"},
        False,
        id="boolean_false_vs_word",
    ),
    pytest.param(
        YesNoQuestion(instructions="Is the order total above 1000 USD?"),
        {"order_total_usd": 1240},
        {"order_total_usd": "1240"},
        True,
        id="number_vs_numeric_string",
    ),
    pytest.param(
        YesNoQuestion(instructions="Was the customer charged more than once for this order?"),
        {"order": {"order_id": "A-104", "charges": [{"amount_usd": 49, "status": "captured"}, {"amount_usd": 49, "status": "captured"}]}},
        {
            "order.order_id": "A-104",
            "order.charges.0.amount_usd": "49",
            "order.charges.0.status": "captured",
            "order.charges.1.amount_usd": "49",
            "order.charges.1.status": "captured",
        },
        True,
        id="nested_vs_flattened_strings",
    ),
]


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


@pytest.mark.judgment
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestJudgmentStateShapes:
    @pytest.mark.parametrize("case", SHAPE_CASES)
    async def test_the_verdict_follows_the_value_in_each_shape(self, judgment_combo: ModelCombo, job_metadata: JobMetadata, case: _ShapeCase) -> None:
        """The state a PipeJudge sends has the expected shape, and the verdict flips with the value inside it."""
        yes_state = _state(case.yes_inputs)
        assert yes_state == case.expected_yes_state

        yes_probability = await _probability_of_yes(judgment_combo=judgment_combo, job_metadata=job_metadata, state=yes_state, question=case.question)
        no_probability = await _probability_of_yes(
            judgment_combo=judgment_combo, job_metadata=job_metadata, state=_state(case.no_inputs), question=case.question
        )
        print(f"yes side {yes_probability:.3f}, no side {no_probability:.3f}")

        assert yes_probability >= CLEAR_YES, f"The yes-side state was not read as yes: {yes_probability:.3f}"
        assert no_probability <= CLEAR_NO, f"The no-side state was not read as no: {no_probability:.3f}"

    @pytest.mark.parametrize(("question", "typed_state", "alternative_state", "expected_yes"), EQUIVALENT_SHAPES)
    async def test_the_typed_shape_reads_like_its_alternative(
        self,
        judgment_combo: ModelCombo,
        job_metadata: JobMetadata,
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
        print(f"typed {typed_probability:.3f}, alternative {alternative_probability:.3f}")

        for label, probability in (("typed", typed_probability), ("alternative", alternative_probability)):
            if expected_yes:
                assert probability >= CLEAR_YES, f"The {label} shape was not read as yes: {probability:.3f}"
            else:
                assert probability <= CLEAR_NO, f"The {label} shape was not read as no: {probability:.3f}"
