from typing import Any

import pytest

from pipelex import log, pretty_print
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.memory.input_shaper.data import Person, Question, build_input_specs

# (test_name, concept_ref, multiplicity, provided_value, expected_concept_ref, expected_list_content)
MULTIPLICITY_CASES: list[tuple[str, str, VariableMultiplicity | None, Any, str, ListContent[StuffContent]]] = [
    # Variable list, element-wise shaping into ListContent[declared].
    (
        "variable-list-refining",
        "shaper_test.Question",
        True,
        ["a", "b"],
        "shaper_test.Question",
        ListContent(items=[Question(text="a"), Question(text="b")]),
    ),
    (
        "variable-list-native-text",
        "native.Text",
        True,
        ["a", "b"],
        "native.Text",
        ListContent(items=[TextContent(text="a"), TextContent(text="b")]),
    ),
    # A single bare value auto-wraps into a one-item list (D2).
    (
        "variable-list-auto-wrap-single",
        "shaper_test.Question",
        True,
        "solo",
        "shaper_test.Question",
        ListContent(items=[Question(text="solo")]),
    ),
    # An empty list is legal and yields an empty ListContent typed with the declared item concept (D2).
    (
        "variable-list-empty",
        "shaper_test.Question",
        True,
        [],
        "shaper_test.Question",
        ListContent(items=[]),
    ),
    # Fixed count [N] validates the count; a single value satisfies [1].
    (
        "fixed-count-two",
        "shaper_test.Question",
        2,
        ["a", "b"],
        "shaper_test.Question",
        ListContent(items=[Question(text="a"), Question(text="b")]),
    ),
    (
        "fixed-count-one-single",
        "shaper_test.Question",
        1,
        "solo",
        "shaper_test.Question",
        ListContent(items=[Question(text="solo")]),
    ),
    # A list of dicts shapes element-wise into a structured list, no envelope.
    (
        "variable-list-of-dicts",
        "shaper_test.Person",
        True,
        [{"name": "Alice"}, {"name": "Bob"}],
        "shaper_test.Person",
        ListContent(items=[Person(name="Alice"), Person(name="Bob")]),
    ),
]


class TestInputShaperMultiplicity:
    @pytest.mark.parametrize(
        ("test_name", "concept_ref", "multiplicity", "provided_value", "expected_concept_ref", "expected_list_content"),
        MULTIPLICITY_CASES,
    )
    def test_multiplicity_case(
        self,
        test_name: str,
        concept_ref: str,
        multiplicity: VariableMultiplicity | None,
        provided_value: Any,
        expected_concept_ref: str,
        expected_list_content: ListContent[StuffContent],
    ) -> None:
        log.info(f"Testing multiplicity case: {test_name}")
        input_specs = build_input_specs([("my_input", concept_ref, multiplicity)])

        working_memory = InputShaper.shape({"my_input": provided_value}, input_specs=input_specs)

        stuff = working_memory.root["my_input"]
        pretty_print(stuff, title=f"Result for {test_name}")
        assert stuff.concept.concept_ref == expected_concept_ref, f"Wrong concept for {test_name}"
        # Equality subsumes the type check: a ListContent never equals a non-ListContent content.
        assert stuff.content == expected_list_content, f"Wrong list content for {test_name}"
