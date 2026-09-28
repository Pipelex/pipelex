from typing import Any

import pytest

from pipelex.core.memory.exceptions import (
    ListWhereSingularError,
    WrongScalarKindError,
)
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import Question, ShaperPerson, build_input_specs


class TestInputShaperAnythingEnvelopes:
    @pytest.mark.parametrize("anything_spelling", ["Anything", "native.Anything"])
    @pytest.mark.parametrize(
        ("content", "expected_content"),
        [
            ({}, JSONContent(json_obj={})),
            ("hi", TextContent(text="hi")),
            (4.2, NumberContent(number=4.2)),
            (False, YesNoContent(yes_no=False)),
        ],
    )
    def test_anything_envelope_is_the_bare_value(self, anything_spelling: str, content: Any, expected_content: StuffContent) -> None:
        """An `Anything` envelope's content is shaped exactly as the same bare value would be (R1)."""
        input_specs = build_input_specs([("payload", "native.Anything", None)])
        provided = {"concept": anything_spelling, "content": content}

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.Anything"
        assert stuff.content == expected_content

    def test_anything_envelope_around_a_list_at_a_plural_slot(self) -> None:
        input_specs = build_input_specs([("payload", "native.Anything", True)])
        provided: dict[str, Any] = {"concept": "native.Anything", "content": [1, "a"]}

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.Anything"
        assert stuff.content == ListContent(items=[NumberContent(number=1), TextContent(text="a")])

    def test_anything_envelope_around_a_list_at_a_single_slot_raises(self) -> None:
        """The envelope does not lift D2: a single `Anything` slot never holds a list."""
        input_specs = build_input_specs([("payload", "native.Anything", None)])
        provided: dict[str, Any] = {"concept": "native.Anything", "content": [1, "a"]}

        with pytest.raises(ListWhereSingularError, match="declares a single"):
            InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

    @pytest.mark.parametrize(
        ("provided", "expected_concept_ref", "expected_content"),
        [
            ({"concept": "Text", "content": "hi"}, "native.Text", TextContent(text="hi")),
            ({"concept": "native.JSON", "content": {"json_obj": {"a": 1}}}, "native.JSON", JSONContent(json_obj={"a": 1})),
            ({"concept": "shaper_test.ShaperPerson", "content": {"name": "Ada"}}, "shaper_test.ShaperPerson", ShaperPerson(name="Ada")),
            ({"concept": "Image", "content": {"url": "photo.jpg"}}, "native.Image", ImageContent(url="photo.jpg")),
        ],
    )
    def test_typed_envelope_at_an_anything_slot_keeps_its_concept(
        self, provided: dict[str, Any], expected_concept_ref: str, expected_content: StuffContent
    ) -> None:
        """R2 and D6: every concept satisfies `Anything`, and the explicit, more specific concept wins."""
        input_specs = build_input_specs([("payload", "native.Anything", None)])

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == expected_concept_ref
        assert stuff.content == expected_content

    def test_prebuilt_content_at_an_anything_slot_keeps_its_inferred_concept(self) -> None:
        input_specs = build_input_specs([("payload", "native.Anything", None)])

        working_memory = InputShaper.shape(
            {"payload": Question(text="Why?")}, input_specs=input_specs, search_scope="shaper_test", concept_provider=get_concept_library()
        )

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "shaper_test.Question"
        assert stuff.content == Question(text="Why?")

    def test_list_of_prebuilt_contents_of_different_kinds_at_anything_list(self) -> None:
        """Each prebuilt item is compat-checked against `Anything`, so a heterogeneous list is fine."""
        input_specs = build_input_specs([("payload", "native.Anything", True)])
        provided: list[StuffContent] = [TextContent(text="a"), NumberContent(number=1)]

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.Anything"
        assert stuff.content == ListContent(items=[TextContent(text="a"), NumberContent(number=1)])

    def test_a_prebuilt_list_of_different_kinds_at_anything_list_is_the_list_of_its_items(self) -> None:
        """A mixed `ListContent` infers no single concept, so it is read as the bare list of its items."""
        input_specs = build_input_specs([("payload", "native.Anything", True)])
        prebuilt: ListContent[StuffContent] = ListContent(items=[TextContent(text="a"), NumberContent(number=1)])

        working_memory = InputShaper.shape({"payload": prebuilt}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.Anything"
        assert stuff.content == prebuilt

    def test_a_prebuilt_list_of_different_kinds_at_a_single_anything_slot_raises(self) -> None:
        input_specs = build_input_specs([("payload", "native.Anything", None)])
        prebuilt: ListContent[StuffContent] = ListContent(items=[TextContent(text="a"), NumberContent(number=1)])

        with pytest.raises(ListWhereSingularError, match="declares a single"):
            InputShaper.shape({"payload": prebuilt}, input_specs=input_specs, concept_provider=get_concept_library())

    def test_nested_envelope_escape_holds_an_envelope_shaped_object(self) -> None:
        """An object keyed exactly `concept` and `content` travels as raw data inside an `Anything` envelope."""
        input_specs = build_input_specs([("payload", "native.Anything", None)])
        provided = {"concept": "native.Anything", "content": {"concept": "x", "content": "y"}}

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.Anything"
        assert stuff.content == JSONContent(json_obj={"concept": "x", "content": "y"})

    def test_anything_envelope_content_is_raw_at_every_depth(self) -> None:
        """R10's escape: inside an `Anything` envelope, an envelope-shaped list item is raw data."""
        input_specs = build_input_specs([("payload", "native.Anything", True)])
        envelope_shaped_item = {"concept": "Image", "content": {"url": "photo.jpg"}}
        provided: dict[str, Any] = {"concept": "native.Anything", "content": [envelope_shaped_item, "caption"]}

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.Anything"
        assert stuff.content == ListContent(items=[JSONContent(json_obj=envelope_shaped_item), TextContent(text="caption")])

    def test_anything_envelope_at_a_dynamic_slot_keeps_its_concept(self) -> None:
        """`Anything` satisfies `Dynamic`, so the envelope is honoured there too, and read as R1 reads it."""
        input_specs = build_input_specs([("payload", "native.Dynamic", None)])
        provided = {"concept": "native.Anything", "content": {"a": 1}}

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.Anything"
        assert stuff.content == JSONContent(json_obj={"a": 1})

    def test_anything_envelope_around_a_prebuilt_list_is_the_list_of_its_items(self) -> None:
        """A prebuilt `ListContent` is the same value as the bare list of its items (R5 reads it by R1 and R3)."""
        prebuilt: ListContent[TextContent] = ListContent(items=[TextContent(text="a"), TextContent(text="b")])
        provided: dict[str, Any] = {"concept": "native.Anything", "content": prebuilt}

        for multiplicity in (True, 2):
            input_specs = build_input_specs([("payload", "native.Anything", multiplicity)])
            working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())
            assert working_memory.root["payload"].content == prebuilt

        single_specs = build_input_specs([("payload", "native.Anything", None)])
        with pytest.raises(ListWhereSingularError):
            InputShaper.shape({"payload": provided}, input_specs=single_specs, concept_provider=get_concept_library())

    def test_a_prebuilt_list_as_a_list_item_is_refused(self) -> None:
        """An item of a plural slot that is itself a list is refused, whether it is a bare array or a `ListContent`."""
        input_specs = build_input_specs([("items", "native.Text", True)])
        provided: list[ListContent[TextContent]] = [ListContent(items=[TextContent(text="a"), TextContent(text="b")])]

        with pytest.raises(WrongScalarKindError, match="a single value, not a list"):
            InputShaper.shape({"items": provided}, input_specs=input_specs, concept_provider=get_concept_library())

    def test_anything_envelope_at_a_dynamic_slot_takes_its_multiplicity_from_its_content(self) -> None:
        """At a `Dynamic` slot the signature cannot say list or single, so the content does, as for every other envelope."""
        input_specs = build_input_specs([("payload", "native.Dynamic", None)])
        provided = {"concept": "native.Anything", "content": [1, 2]}

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.Anything"
        assert stuff.content == ListContent(items=[NumberContent(number=1), NumberContent(number=2)])
