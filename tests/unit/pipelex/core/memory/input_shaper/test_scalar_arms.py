import datetime
from typing import Any

import pytest

from pipelex import log, pretty_print
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import (
    Deadline,
    Exhibit,
    Payload,
    Photo,
    Priority,
    Question,
    ShaperInvoice,
    Verdict,
    build_input_specs,
)

# (test_name, concept_ref, provided_value, expected_concept_ref, expected_content)
SCALAR_ARM_CASES: list[tuple[str, str, Any, str, StuffContent]] = [
    # D5 Text-refining: a bare string becomes the DECLARED concept, typed as its refining subclass.
    ("text-native", "native.Text", "hello", "native.Text", TextContent(text="hello")),
    ("text-refining", "shaper_test.Question", "What are the fees?", "shaper_test.Question", Question(text="What are the fees?")),
    # D5 Number-refining: int and float accepted (bool excluded, see errors).
    ("number-native-int", "native.Number", 3, "native.Number", NumberContent(number=3)),
    ("number-native-float", "native.Number", 3.5, "native.Number", NumberContent(number=3.5)),
    ("number-refining", "shaper_test.Priority", 3, "shaper_test.Priority", Priority(number=3)),
    # D5 YesNo-refining: a bare boolean.
    ("yesno-native-true", "native.YesNo", True, "native.YesNo", YesNoContent(yes_no=True)),
    ("yesno-refining-false", "shaper_test.Verdict", False, "shaper_test.Verdict", Verdict(yes_no=False)),
    # D5 Date-refining: an ISO string or a date object.
    ("date-native-iso", "native.Date", "2026-07-07", "native.Date", DateContent(date=datetime.date(2026, 7, 7))),
    ("date-refining-obj", "shaper_test.Deadline", datetime.date(2026, 8, 6), "shaper_test.Deadline", Deadline(date=datetime.date(2026, 8, 6))),
    # D3/D5 Image/Document-refining: a bare string (URL/path) or a {"url": ...} dict.
    ("image-refining-str", "shaper_test.Photo", "photo.jpg", "shaper_test.Photo", Photo(url="photo.jpg")),
    ("image-native-dict", "native.Image", {"url": "pic.png"}, "native.Image", ImageContent(url="pic.png")),
    ("document-refining-str", "shaper_test.Exhibit", "doc.pdf", "shaper_test.Exhibit", Exhibit(url="doc.pdf")),
    # D5 Structured: a bare dict validated by pydantic against the declared structure class.
    (
        "structured-dict",
        "shaper_test.ShaperInvoice",
        {"invoice_number": "INV-001", "amount": 1250.0},
        "shaper_test.ShaperInvoice",
        ShaperInvoice(invoice_number="INV-001", amount=1250.0),
    ),
    # D5 Dynamic and the out-of-matrix natives: bottom-up passthrough.
    ("dynamic-str-bottom-up", "native.Dynamic", "hi", "native.Text", TextContent(text="hi")),
    ("html-out-of-matrix-bottom-up", "native.Html", "hi", "native.Text", TextContent(text="hi")),
    # R1 Anything: the slot keeps its declared concept, and the content is the natural one for the
    # value's JSON type. Nothing is guessed from a string's text: a URL or an ISO date stays text.
    ("anything-string", "native.Anything", "hi", "native.Anything", TextContent(text="hi")),
    ("anything-url-string-stays-text", "native.Anything", "photo.jpg", "native.Anything", TextContent(text="photo.jpg")),
    ("anything-iso-string-stays-text", "native.Anything", "2026-07-07", "native.Anything", TextContent(text="2026-07-07")),
    ("anything-int", "native.Anything", 3, "native.Anything", NumberContent(number=3)),
    ("anything-float", "native.Anything", 3.5, "native.Anything", NumberContent(number=3.5)),
    ("anything-zero-is-a-number", "native.Anything", 0, "native.Anything", NumberContent(number=0)),
    # A boolean is never a number, although bool subclasses int.
    ("anything-true", "native.Anything", True, "native.Anything", YesNoContent(yes_no=True)),
    ("anything-false", "native.Anything", False, "native.Anything", YesNoContent(yes_no=False)),
    # The published fill-in template's value, `{}`, shapes.
    ("anything-empty-object", "native.Anything", {}, "native.Anything", JSONContent(json_obj={})),
    (
        "anything-nested-object",
        "native.Anything",
        {"a": {"b": [1, "two", None]}},
        "native.Anything",
        JSONContent(json_obj={"a": {"b": [1, "two", None]}}),
    ),
    # An object is read literally: `json_obj` is JSONContent's field name, not something a caller spells.
    (
        "anything-json-obj-key-taken-literally",
        "native.Anything",
        {"json_obj": {"a": 1}},
        "native.Anything",
        JSONContent(json_obj={"json_obj": {"a": 1}}),
    ),
    # R7 JSON: a bare object is the JSON object itself, read literally.
    ("json-object", "native.JSON", {"a": 1}, "native.JSON", JSONContent(json_obj={"a": 1})),
    ("json-empty-object", "native.JSON", {}, "native.JSON", JSONContent(json_obj={})),
    ("json-nested-object", "native.JSON", {"a": {"b": [1, {"c": None}]}}, "native.JSON", JSONContent(json_obj={"a": {"b": [1, {"c": None}]}})),
    ("json-obj-key-taken-literally", "native.JSON", {"json_obj": {"a": 1}}, "native.JSON", JSONContent(json_obj={"json_obj": {"a": 1}})),
    # A concept refining JSON is built through its own class.
    ("json-refining", "shaper_test.Payload", {"order_id": 7}, "shaper_test.Payload", Payload(json_obj={"order_id": 7})),
    # TOML temporal literals (inputs files only).
    ("anything-toml-date", "native.Anything", datetime.date(2026, 7, 7), "native.Anything", DateContent(date=datetime.date(2026, 7, 7))),
    (
        "anything-toml-datetime",
        "native.Anything",
        datetime.datetime(2026, 7, 7, 15, 40),
        "native.Anything",
        DateContent(date=datetime.date(2026, 7, 7), time=datetime.time(15, 40)),
    ),
    ("anything-toml-time", "native.Anything", datetime.time(15, 40), "native.Anything", TimeContent(time=datetime.time(15, 40))),
]


class TestInputShaperScalarArms:
    @pytest.mark.parametrize(
        ("test_name", "concept_ref", "provided_value", "expected_concept_ref", "expected_content"),
        SCALAR_ARM_CASES,
    )
    def test_scalar_arm(
        self,
        test_name: str,
        concept_ref: str,
        provided_value: Any,
        expected_concept_ref: str,
        expected_content: StuffContent,
    ) -> None:
        log.info(f"Testing scalar arm case: {test_name}")
        input_specs = build_input_specs([("my_input", concept_ref, None)])

        working_memory = InputShaper.shape(
            {"my_input": provided_value}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None
        )

        stuff = working_memory.root["my_input"]
        pretty_print(stuff, title=f"Result for {test_name}")
        assert stuff.concept.concept_ref == expected_concept_ref, f"Wrong concept for {test_name}"
        assert stuff.content == expected_content, f"Wrong content for {test_name}"
