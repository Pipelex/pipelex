import datetime
from typing import Any

import pytest

from pipelex import log, pretty_print
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import Deadline, Question, ShaperPerson, build_input_specs

# (test_name, concept_ref, multiplicity, provided_value, expected_concept_ref, expected_content)
MULTIPLICITY_CASES: list[tuple[str, str, VariableMultiplicity | None, Any, str, StuffContent]] = [
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
    # Fixed count [N] validates the count.
    (
        "fixed-count-two",
        "shaper_test.Question",
        2,
        ["a", "b"],
        "shaper_test.Question",
        ListContent(items=[Question(text="a"), Question(text="b")]),
    ),
    # `[1]` is the single form, not a one-item list: the shaper builds the item itself, and a list
    # payload is refused there exactly as it is under a bare declaration.
    (
        "fixed-count-one-is-single",
        "shaper_test.Question",
        1,
        "solo",
        "shaper_test.Question",
        Question(text="solo"),
    ),
    # A list of dicts shapes element-wise into a structured list, no envelope.
    (
        "variable-list-of-dicts",
        "shaper_test.ShaperPerson",
        True,
        [{"name": "Alice"}, {"name": "Bob"}],
        "shaper_test.ShaperPerson",
        ListContent(items=[ShaperPerson(name="Alice"), ShaperPerson(name="Bob")]),
    ),
    # A top-level list of bare date objects (e.g. a TOML `deadlines = [2026-01-01, 2026-02-02]` array
    # the loader leaves untouched) shapes element-wise into ListContent[DateContent] under a declared
    # Date-refining `[]` input — the case `case1-bare-date-arm-gap.md` deferred, now closed by the shaper.
    (
        "variable-list-of-date-objects",
        "shaper_test.Deadline",
        True,
        [datetime.date(2026, 1, 1), datetime.date(2026, 2, 2)],
        "shaper_test.Deadline",
        ListContent(items=[Deadline(date=datetime.date(2026, 1, 1)), Deadline(date=datetime.date(2026, 2, 2))]),
    ),
    # R3 Anything[]: shaped element-wise, and the items may differ in JSON type.
    (
        "anything-list-mixed",
        "native.Anything",
        True,
        ["a", 1, True, {"k": 1}],
        "native.Anything",
        ListContent(items=[TextContent(text="a"), NumberContent(number=1), YesNoContent(yes_no=True), JSONContent(json_obj={"k": 1})]),
    ),
    ("anything-list-empty", "native.Anything", True, [], "native.Anything", ListContent(items=[])),
    ("anything-list-auto-wrap-single", "native.Anything", True, "solo", "native.Anything", ListContent(items=[TextContent(text="solo")])),
    # A single object is wrapped too, rather than read as a list.
    ("anything-list-auto-wrap-object", "native.Anything", True, {"a": 1}, "native.Anything", ListContent(items=[JSONContent(json_obj={"a": 1})])),
    (
        "anything-fixed-count-two",
        "native.Anything",
        2,
        [1, "b"],
        "native.Anything",
        ListContent(items=[NumberContent(number=1), TextContent(text="b")]),
    ),
    # R7 JSON[]: each object in turn, a single object wrapped, an empty list legal.
    (
        "json-list-of-objects",
        "native.JSON",
        True,
        [{"a": 1}, {"b": 2}],
        "native.JSON",
        ListContent(items=[JSONContent(json_obj={"a": 1}), JSONContent(json_obj={"b": 2})]),
    ),
    ("json-list-auto-wrap-object", "native.JSON", True, {"a": 1}, "native.JSON", ListContent(items=[JSONContent(json_obj={"a": 1})])),
    ("json-list-empty", "native.JSON", True, [], "native.JSON", ListContent(items=[])),
]


class TestInputShaperMultiplicity:
    @pytest.mark.parametrize(
        ("test_name", "concept_ref", "multiplicity", "provided_value", "expected_concept_ref", "expected_content"),
        MULTIPLICITY_CASES,
    )
    def test_multiplicity_case(
        self,
        test_name: str,
        concept_ref: str,
        multiplicity: VariableMultiplicity | None,
        provided_value: Any,
        expected_concept_ref: str,
        expected_content: StuffContent,
    ) -> None:
        log.info(f"Testing multiplicity case: {test_name}")
        input_specs = build_input_specs([("my_input", concept_ref, multiplicity)])

        working_memory = InputShaper.shape(
            {"my_input": provided_value}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None
        )

        stuff = working_memory.root["my_input"]
        pretty_print(stuff, title=f"Result for {test_name}")
        assert stuff.concept.concept_ref == expected_concept_ref, f"Wrong concept for {test_name}"
        # Equality subsumes the type check: a ListContent never equals a non-ListContent content.
        assert stuff.content == expected_content, f"Wrong content for {test_name}"
