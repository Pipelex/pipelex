import datetime
from typing import Any

import pytest

from pipelex import log, pretty_print
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from tests.unit.pipelex.core.memory.input_shaper.data import (
    Deadline,
    Exhibit,
    Invoice,
    Photo,
    Priority,
    Question,
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
        "shaper_test.Invoice",
        {"invoice_number": "INV-001", "amount": 1250.0},
        "shaper_test.Invoice",
        Invoice(invoice_number="INV-001", amount=1250.0),
    ),
    # D5 Dynamic/Anything/out-of-matrix natives: bottom-up passthrough (today's behavior).
    ("dynamic-str-bottom-up", "native.Dynamic", "hi", "native.Text", TextContent(text="hi")),
    ("anything-str-bottom-up", "native.Anything", "hi", "native.Text", TextContent(text="hi")),
    ("html-out-of-matrix-bottom-up", "native.Html", "hi", "native.Text", TextContent(text="hi")),
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

        working_memory = InputShaper.shape({"my_input": provided_value}, input_specs=input_specs)

        stuff = working_memory.root["my_input"]
        pretty_print(stuff, title=f"Result for {test_name}")
        assert stuff.concept.concept_ref == expected_concept_ref, f"Wrong concept for {test_name}"
        assert stuff.content == expected_content, f"Wrong content for {test_name}"
