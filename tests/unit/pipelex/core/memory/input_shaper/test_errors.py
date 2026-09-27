from typing import Any

import pytest

from pipelex import log
from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.core.memory.exceptions import (
    ExplicitConceptIncompatibleError,
    InputShapingError,
    ListWhereSingularError,
    MultiplicityCountMismatchError,
    NullInputError,
    StructureValidationError,
    UnknownInputNameError,
    WrongScalarKindError,
)
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import build_input_specs

# (test_name, concept_ref, multiplicity, provided_value, expected_exception, error_match)
# Every case here is a D4 shaping error whose message carries the rendered expected-shape template
# (asserted unconditionally below). The D8 unknown-name error, which carries no shape, is tested separately.
ERROR_CASES: list[tuple[str, str, VariableMultiplicity | None, Any, type[InputShapingError], str]] = [
    # D5 wrong scalar kind — no cross-type parse: "42" stays a string, never a number.
    ("wrong-str-for-number", "shaper_test.Priority", None, "42", WrongScalarKindError, "expects a number"),
    ("wrong-int-for-text", "native.Text", None, 5, WrongScalarKindError, "expects a string"),
    ("wrong-bool-for-text", "native.Text", None, True, WrongScalarKindError, "expects a string"),
    # D9 bool never leaks into the Number arm (bool is a subclass of int).
    ("wrong-bool-for-number", "shaper_test.Priority", None, True, WrongScalarKindError, "expects a number"),
    # D9 a top-level null is a hard error (absence = omit the key).
    ("null-top-level", "native.Text", None, None, NullInputError, "null"),
    # Same rule on the one concept that declares no structure class: `native.Anything` reaches the
    # expected-shape render (this arm fires before the D5 `InputKind.DYNAMIC` short-circuit), so the
    # hint has to be renderable without resolving a class — it used to raise while building the error.
    ("null-top-level-anything", "native.Anything", None, None, NullInputError, "null"),
    # D2 a list where a singular is declared is ambiguous.
    ("list-where-singular", "shaper_test.Question", None, ["a", "b"], ListWhereSingularError, "single"),
    # `[1]` IS the singular declaration, so it refuses a list on the same grounds — including a
    # one-item list, which would otherwise look like it "fits" the count.
    ("list-where-fixed-count-one", "shaper_test.Question", 1, ["a", "b"], ListWhereSingularError, "single"),
    ("one-item-list-where-fixed-count-one", "shaper_test.Question", 1, ["solo"], ListWhereSingularError, "single"),
    # D2 fixed-count mismatch — too few, and a single value for [2].
    ("count-mismatch-list-too-few", "shaper_test.Question", 2, ["a"], MultiplicityCountMismatchError, "exactly 2"),
    ("count-mismatch-single-for-two", "shaper_test.Question", 2, "solo", MultiplicityCountMismatchError, "exactly 2"),
    # D4 structure validation — a missing required field surfaces as a shaping error.
    ("structure-missing-field", "shaper_test.ShaperInvoice", None, {"invoice_number": "INV-1"}, StructureValidationError, "could not be built"),
    # D4 a non-ISO date string is the right kind but an invalid value.
    ("non-iso-date", "shaper_test.Deadline", None, "March 7, 2026", StructureValidationError, "ISO 8601"),
    # R3 Anything keeps D2 and D9: a list at a single slot, a count mismatch, a null anywhere.
    ("anything-list-where-singular", "native.Anything", None, [1, 2], ListWhereSingularError, "single"),
    ("anything-count-mismatch", "native.Anything", 2, [1], MultiplicityCountMismatchError, "exactly 2"),
    ("anything-null-item", "native.Anything", True, [1, None], WrongScalarKindError, "provided null"),
    ("anything-nested-list-item", "native.Anything", True, [[1, 2]], WrongScalarKindError, "a list of 2 item"),
    ("anything-null-envelope-content", "native.Anything", None, {"concept": "native.Anything", "content": None}, NullInputError, "null"),
    # R1 a Python caller's value that is not JSON at all.
    ("anything-not-a-json-value", "native.Anything", None, {1, 2}, WrongScalarKindError, "a value of type set"),
    # An object holding a value that is not JSON is a typed refusal, not a raw TypeError from the validator.
    ("anything-object-holding-a-non-json-value", "native.Anything", None, {"a": object()}, StructureValidationError, "not valid JSON"),
    # R10 an item of a bare list shaped like an envelope is refused, and the message says how to type a list.
    (
        "anything-envelope-shaped-item",
        "native.Anything",
        True,
        [{"concept": "Image", "content": {"url": "photo.jpg"}}, "caption"],
        WrongScalarKindError,
        "wrap the whole list in one",
    ),
    # R5 an Anything envelope is not known to satisfy anything narrower.
    (
        "anything-envelope-at-text-slot",
        "native.Text",
        None,
        {"concept": "native.Anything", "content": "hi"},
        ExplicitConceptIncompatibleError,
        "not compatible",
    ),
    # R7 a JSON slot takes a JSON object and nothing else. A string used to become native.Text.
    ("json-string", "native.JSON", None, "hi", WrongScalarKindError, "expects a JSON object"),
    ("json-number", "native.JSON", None, 3, WrongScalarKindError, "expects a JSON object"),
    ("json-boolean", "native.JSON", None, True, WrongScalarKindError, "expects a JSON object"),
    ("json-list-where-singular", "native.JSON", None, [{"a": 1}], ListWhereSingularError, "single"),
    ("json-array-item", "native.JSON", True, [{"a": 1}, [1, 2]], WrongScalarKindError, "expects a JSON object"),
    (
        "json-envelope-shaped-item",
        "native.JSON",
        True,
        [{"concept": "JSON", "content": {"json_obj": {}}}],
        WrongScalarKindError,
        "wrap the whole list in one",
    ),
    # D6 an explicit envelope naming an incompatible concept.
    (
        "explicit-incompatible",
        "shaper_test.Priority",
        None,
        {"concept": "shaper_test.Question", "content": "hi"},
        ExplicitConceptIncompatibleError,
        "not compatible",
    ),
]


class TestInputShaperErrors:
    @pytest.mark.parametrize(
        ("test_name", "concept_ref", "multiplicity", "provided_value", "expected_exception", "error_match"),
        ERROR_CASES,
    )
    def test_error_case(
        self,
        test_name: str,
        concept_ref: str,
        multiplicity: VariableMultiplicity | None,
        provided_value: Any,
        expected_exception: type[InputShapingError],
        error_match: str,
    ) -> None:
        log.info(f"Testing error case: {test_name}")
        input_specs = build_input_specs([("my_input", concept_ref, multiplicity)])

        with pytest.raises(expected_exception, match=error_match) as exc_info:
            InputShaper.shape({"my_input": provided_value}, input_specs=input_specs, concept_provider=get_concept_library())

        # D4 mandates the rendered expected-shape template appears in every shaping-error message.
        assert "Expected shape:" in str(exc_info.value), f"Missing rendered shape for {test_name}"

    def test_unknown_input_name_is_error(self) -> None:
        """D8: a provided name absent from the signature is a hard error that lists the declared names."""
        input_specs = build_input_specs([("question", "native.Text", None)])

        with pytest.raises(UnknownInputNameError, match="not declared") as exc_info:
            InputShaper.shape({"quesion": "typo"}, input_specs=input_specs, concept_provider=get_concept_library())

        message = str(exc_info.value)
        assert "'question'" in message, "Unknown-name error should list the declared inputs"
        assert "'quesion'" in message, "Unknown-name error should name the offending input"


class TestInputShaperFallbackRefusal:
    """R8: a value the bottom-up fallback has no reading for is a typed input error naming the slot."""

    @pytest.mark.parametrize(
        ("concept_ref", "multiplicity"),
        [
            ("native.Dynamic", None),
            ("native.Dynamic", True),
            ("native.Composite", True),
            ("native.Html", True),
            ("native.TextAndImages", True),
            ("native.SearchResult", True),
            ("native.Page", True),
        ],
    )
    def test_a_list_of_objects_is_refused_naming_the_input(self, concept_ref: str, multiplicity: VariableMultiplicity | None) -> None:
        input_specs = build_input_specs([("records", concept_ref, multiplicity)])
        records_input: dict[str, Any] = {"records": [{"a": 1}, {"b": 2}]}

        with pytest.raises(StructureValidationError) as exc_info:
            InputShaper.shape(records_input, input_specs=input_specs, concept_provider=get_concept_library())

        error = exc_info.value
        message = str(error)
        assert "Input 'records'" in message
        assert f"'{concept_ref}'" in message
        assert "a list of 2 item(s)" in message
        assert "Expected shape:" in message
        # The factory's own text, with its `typing.Union[...]` spelling of what it accepts, stays on
        # the chain as the cause and out of what a caller reads.
        assert "typing.Union" not in message
        assert isinstance(error.__cause__, StuffFactoryError)
        assert error.error_domain == ErrorDomain.INPUT
        # The fix is on the author's side: the declaration, and no envelope.
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert "'JSON[]'" in error.user_action.detail
        assert "envelope" not in error.user_action.detail

    def test_a_bare_number_at_a_dynamic_slot_is_refused_naming_the_input(self) -> None:
        input_specs = build_input_specs([("payload", "native.Dynamic", None)])
        payload_input: dict[str, Any] = {"payload": 3}

        with pytest.raises(StructureValidationError, match=r"Input 'payload' could not be built as 'native\.Dynamic'") as exc_info:
            InputShaper.shape(payload_input, input_specs=input_specs, concept_provider=get_concept_library())

        assert "a number (3)" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, StuffFactoryError)
