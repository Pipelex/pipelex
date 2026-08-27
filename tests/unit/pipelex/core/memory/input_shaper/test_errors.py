from typing import Any

import pytest

from pipelex import log
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
