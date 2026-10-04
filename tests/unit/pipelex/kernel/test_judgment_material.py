"""The material a judgment is asked over: one entry per input, read off its content's class, files beside the state."""

import datetime
from typing import Any

import pytest
from pydantic import Field

from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.judgment_ops import build_judgment_material


class _ReportWithNestedContents(StructuredContent):
    """A structure whose fields are typed as the content base, so they hold whichever content subclass a run put there."""

    payload: StuffContent
    extras: list[StuffContent]


class _Invoice(StructuredContent):
    """A structure a dotted input reaches into."""

    total: float
    note: str | None = None
    scan: ImageContent | None = None
    lines: list[TextContent] = Field(default_factory=list[TextContent])


def _memory(contents: dict[str, StuffContent]) -> WorkingMemory:
    """A memory holding each content under its name.

    The concept is `Anything` for every one, because the material is read off the content's class and
    never off its concept: that is what keeps the kernel free of the concept library.
    """
    anything = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
    stuffs = [StuffFactory.make_stuff(concept=anything, content=content, name=name) for name, content in contents.items()]
    return WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=stuffs)


class TestJudgmentMaterial:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            pytest.param(TextContent(text="the roof leaks"), "the roof leaks", id="text"),
            pytest.param(MarkdownContent(text="# Leak"), "# Leak", id="text_refinement"),
            pytest.param(NumberContent(number=42), 42, id="number"),
            pytest.param(YesNoContent(yes_no=False, probability=0.2), False, id="yes_no_as_its_boolean"),
            pytest.param(DateContent(date=datetime.date(2026, 10, 4)), "2026-10-04", id="date"),
            pytest.param(TimeContent(time=datetime.time(15, 40)), "15:40:00", id="time"),
            pytest.param(JSONContent(json_obj={"a": 1}), {"a": 1}, id="json"),
            pytest.param(
                ChoiceContent(choice="billing", confidence=0.7), {"choice": "billing", "confidence": 0.7}, id="choice_without_absent_members"
            ),
            pytest.param(RatingContent(level=2), {"level": 2}, id="rating"),
            pytest.param(HtmlContent(inner_html="<p>hi</p>"), {"inner_html": "<p>hi</p>"}, id="other_structure"),
            pytest.param(ListContent(items=[TextContent(text="a"), TextContent(text="b")]), ["a", "b"], id="list"),
        ],
    )
    def test_a_non_file_input_is_a_member_of_the_state(self, content: StuffContent, expected: Any) -> None:
        state, images, documents = build_judgment_material(memory=_memory({"material": content}), input_names=["material"])

        assert state == {"material": expected}
        assert images == {}
        assert documents == {}

    def test_the_state_is_keyed_by_the_declared_names_in_their_order(self) -> None:
        memory = _memory({"message": TextContent(text="help"), "count": NumberContent(number=3), "unasked": TextContent(text="ignored")})

        state, _, _ = build_judgment_material(memory=memory, input_names=["count", "message"])

        assert list(state) == ["count", "message"]

    def test_an_absent_optional_input_is_left_out(self) -> None:
        memory = _memory({"message": TextContent(text="help")})
        memory.record_resolved_absence(AbsenceRecord(variable_name="context", kind=AbsenceKind.NOT_PROVIDED, reason="not provided"))

        state, images, documents = build_judgment_material(memory=memory, input_names=["message", "context"])

        assert state == {"message": "help"}
        assert images == {}
        assert documents == {}

    def test_an_optional_input_never_written_is_left_out(self) -> None:
        """An optional input with neither a value nor a recorded absence reaches the step: the presence scan lets it through."""
        memory = _memory({"message": TextContent(text="help")})

        state, images, documents = build_judgment_material(memory=memory, input_names=["message", "context"])

        assert state == {"message": "help"}
        assert images == {}
        assert documents == {}

    def test_an_image_and_a_document_go_to_the_file_channel(self) -> None:
        memory = _memory(
            {
                "photo": ImageContent(url="pipelex-storage://s/photo.png", mime_type="image/png"),
                "claim": DocumentContent(url="pipelex-storage://s/claim.pdf", mime_type="application/pdf"),
                "message": TextContent(text="see attached"),
            }
        )

        state, images, documents = build_judgment_material(memory=memory, input_names=["photo", "claim", "message"])

        assert state == {"message": "see attached"}
        assert images == {"photo": [PromptImageUri(uri="pipelex-storage://s/photo.png", mime_type="image/png")]}
        assert documents == {"claim": [PromptDocumentUri(uri="pipelex-storage://s/claim.pdf", mime_type="application/pdf")]}

    def test_a_list_of_images_and_a_list_of_documents_go_to_the_file_channel_as_lists(self) -> None:
        memory = _memory(
            {
                "photos": ListContent(items=[ImageContent(url="pipelex-storage://s/a.png"), ImageContent(url="pipelex-storage://s/b.png")]),
                "claims": ListContent(items=[DocumentContent(url="pipelex-storage://s/a.pdf")]),
            }
        )

        state, images, documents = build_judgment_material(memory=memory, input_names=["photos", "claims"])

        assert state == {}
        assert [image.uri for image in images["photos"] if isinstance(image, PromptImageUri)] == [
            "pipelex-storage://s/a.png",
            "pipelex-storage://s/b.png",
        ]
        assert [document.uri for document in documents["claims"] if isinstance(document, PromptDocumentUri)] == ["pipelex-storage://s/a.pdf"]

    def test_an_empty_list_is_an_empty_array_in_the_state(self) -> None:
        state, images, _ = build_judgment_material(memory=_memory({"photos": ListContent[ImageContent](items=[])}), input_names=["photos"])

        assert state == {"photos": []}
        assert images == {}

    def test_a_structure_keeps_the_fields_of_the_contents_nested_in_it(self) -> None:
        report = _ReportWithNestedContents(payload=TextContent(text="The roof is on fire"), extras=[NumberContent(number=3)])
        state, _, _ = build_judgment_material(memory=_memory({"report": report}), input_names=["report"])
        assert state == {"report": {"payload": {"text": "The roof is on fire"}, "extras": [{"number": 3}]}}

    def test_a_dotted_input_is_the_value_at_its_path_keyed_by_its_full_name(self) -> None:
        invoice = _Invoice(total=1250.0, note="rush", lines=[TextContent(text="roof"), TextContent(text="gutter")])
        memory = _memory({"invoice": invoice})

        state, images, documents = build_judgment_material(memory=memory, input_names=["invoice.total", "invoice.note", "invoice.lines"])

        assert state == {"invoice.total": 1250.0, "invoice.note": "rush", "invoice.lines": ["roof", "gutter"]}
        assert images == {}
        assert documents == {}

    def test_a_dotted_input_reaching_a_file_goes_to_the_file_channel(self) -> None:
        invoice = _Invoice(total=1.0, scan=ImageContent(url="pipelex-storage://s/scan.png", mime_type="image/png"))

        state, images, _ = build_judgment_material(memory=_memory({"invoice": invoice}), input_names=["invoice.scan"])

        assert state == {}
        assert images == {"invoice.scan": [PromptImageUri(uri="pipelex-storage://s/scan.png", mime_type="image/png")]}

    def test_a_dotted_input_whose_field_or_root_holds_nothing_is_left_out(self) -> None:
        memory = _memory({"message": TextContent(text="help"), "invoice": _Invoice(total=1.0)})

        state, _, _ = build_judgment_material(memory=memory, input_names=["message", "invoice.note", "estimate.total"])

        assert state == {"message": "help"}
