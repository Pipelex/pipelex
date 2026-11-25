from collections.abc import Callable
from typing import Any

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
from tests.unit.pipelex.core.stuffs.stored_value.cases import STORED_HTML, STORED_JSON_OBJ, STORED_TEXT, StoredValueCases

_REFERENCED_CASES: list[tuple[NativeConceptCode, type[StoredValueContent], dict[str, Any]]] = [
    (NativeConceptCode.TEXT, TextContent, StoredValueCases.TEXT_REFERENCE),
    (NativeConceptCode.MARKDOWN, MarkdownContent, StoredValueCases.MARKDOWN_REFERENCE),
    (NativeConceptCode.HTML, HtmlContent, StoredValueCases.HTML_REFERENCE),
    (NativeConceptCode.JSON, JSONContent, StoredValueCases.JSON_REFERENCE),
]


class TestStoredValueSerialization:
    @pytest.fixture(scope="class", autouse=True)
    def _open_library(self, load_empty_library: Callable[[], str]) -> None:
        """A stuff names its concept by ref, and the hydrator resolves it through the current library."""
        load_empty_library()

    @pytest.mark.parametrize(("native_code", "content_class", "reference"), _REFERENCED_CASES)
    def test_a_referenced_content_dumps_its_reference_and_no_value(
        self,
        native_code: NativeConceptCode,
        content_class: type[StoredValueContent],
        reference: dict[str, Any],
    ):
        content = content_class.model_validate(reference)
        expected = {**reference, "css_class": None} if native_code == NativeConceptCode.HTML else reference
        assert content.smart_dump() == expected
        assert content.model_dump(mode="json") == expected

    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (TextContent(text=STORED_TEXT), {"text": STORED_TEXT}),
            (MarkdownContent(text=STORED_TEXT), {"text": STORED_TEXT}),
            (HtmlContent(inner_html=STORED_HTML), {"inner_html": STORED_HTML, "css_class": None}),
            (JSONContent(json_obj=STORED_JSON_OBJ), {"json_obj": STORED_JSON_OBJ}),
        ],
    )
    def test_an_inline_content_dumps_its_value_and_no_reference(self, content: StoredValueContent, expected: dict[str, Any]):
        assert content.smart_dump() == expected

    @pytest.mark.parametrize(("native_code", "content_class", "reference"), _REFERENCED_CASES)
    def test_a_referenced_content_round_trips_through_transport(
        self,
        native_code: NativeConceptCode,
        content_class: type[StoredValueContent],
        reference: dict[str, Any],
    ):
        content = content_class.model_validate(reference)
        working_memory = WorkingMemory()
        working_memory.root["value"] = Stuff(
            stuff_code="test",
            stuff_name="value",
            concept=ConceptFactory.make_native_concept(native_concept_code=native_code),
            content=content,
        )

        raw = working_memory.dump_for_transport()
        hydrated = hydrate_working_memory(raw)

        hydrated_content = hydrated.root["value"].content
        assert type(hydrated_content) is content_class
        assert hydrated_content == content
        assert hydrated_content.smart_dump() == content.smart_dump()
