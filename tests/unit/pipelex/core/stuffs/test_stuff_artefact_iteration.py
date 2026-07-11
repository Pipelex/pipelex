"""Tests for StuffArtefact iterator protocol delegation to ListContent."""

from __future__ import annotations

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.text_content import TextContent


def _make_list_stuff(items: list[TextContent]) -> Stuff:
    """Create a Stuff with ListContent containing TextContent items."""
    return Stuff(
        stuff_code="test_list",
        stuff_name="test_list",
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=ListContent(items=items),
    )


def _make_text_stuff(text: str) -> Stuff:
    """Create a Stuff with TextContent."""
    return Stuff(
        stuff_code="test_text",
        stuff_name="test_text",
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text=text),
    )


class TestStuffArtefactIteration:
    """Tests for StuffArtefact delegation of iterator protocol to content."""

    def test_iter_list_content(self) -> None:
        """Verify that iterating over StuffArtefact delegates to ListContent."""
        items = [
            TextContent(text="Item 1"),
            TextContent(text="Item 2"),
            TextContent(text="Item 3"),
        ]
        stuff = _make_list_stuff(items)
        artefact = StuffArtefact(stuff)

        result = list(artefact)

        assert len(result) == 3
        assert result[0].text == "Item 1"
        assert result[1].text == "Item 2"
        assert result[2].text == "Item 3"

    def test_iter_in_for_loop(self) -> None:
        """Verify that StuffArtefact works in a for loop."""
        items = [
            TextContent(text="A"),
            TextContent(text="B"),
        ]
        stuff = _make_list_stuff(items)
        artefact = StuffArtefact(stuff)

        texts: list[str] = []
        for item in artefact:
            texts.append(item.text)

        assert texts == ["A", "B"]

    def test_iter_non_iterable_raises_type_error(self) -> None:
        """Verify that iterating over non-iterable content raises TypeError."""
        stuff = _make_text_stuff("Plain text")
        artefact = StuffArtefact(stuff)

        with pytest.raises(TypeError, match="not iterable"):
            list(artefact)

    def test_len_list_content(self) -> None:
        """Verify that len() on StuffArtefact delegates to ListContent."""
        items = [
            TextContent(text="Item 1"),
            TextContent(text="Item 2"),
        ]
        stuff = _make_list_stuff(items)
        artefact = StuffArtefact(stuff)

        assert len(artefact) == 2

    def test_len_empty_list(self) -> None:
        """Verify that len() works on empty ListContent."""
        stuff = _make_list_stuff([])
        artefact = StuffArtefact(stuff)

        assert len(artefact) == 0

    def test_len_non_list_raises_type_error(self) -> None:
        """Verify that len() on non-list content raises TypeError."""
        stuff = _make_text_stuff("Plain text")
        artefact = StuffArtefact(stuff)

        with pytest.raises(TypeError, match="does not support len"):
            len(artefact)

    def test_getitem_string_key_still_works(self) -> None:
        """Verify that string key access still works for backward compatibility."""
        items = [TextContent(text="Item")]
        stuff = _make_list_stuff(items)
        artefact = StuffArtefact(stuff)

        # items is a field on ListContent, so it should still be accessible
        assert artefact["items"] == items

    def test_getitem_integer_index_list_content(self) -> None:
        """Verify that integer indexing works on ListContent via StuffArtefact."""
        items = [
            TextContent(text="First"),
            TextContent(text="Second"),
        ]
        stuff = _make_list_stuff(items)
        artefact = StuffArtefact(stuff)

        assert artefact[0].text == "First"
        assert artefact[1].text == "Second"
        assert artefact[-1].text == "Second"

    def test_getitem_slice_list_content(self) -> None:
        """Verify that slicing works on ListContent via StuffArtefact."""
        items = [
            TextContent(text="A"),
            TextContent(text="B"),
            TextContent(text="C"),
        ]
        stuff = _make_list_stuff(items)
        artefact = StuffArtefact(stuff)

        sliced = artefact[0:2]

        assert len(sliced) == 2
        assert sliced[0].text == "A"
        assert sliced[1].text == "B"

    def test_getitem_integer_non_indexable_raises_type_error(self) -> None:
        """Verify that integer indexing on non-indexable content raises TypeError."""
        stuff = _make_text_stuff("Plain text")
        artefact = StuffArtefact(stuff)

        with pytest.raises(TypeError, match="does not support indexing"):
            _ = artefact[0]

    def test_backward_compatibility_items_access(self) -> None:
        """Verify that .items still works for backward compatibility."""
        items = [
            TextContent(text="Item 1"),
            TextContent(text="Item 2"),
        ]
        stuff = _make_list_stuff(items)
        artefact = StuffArtefact(stuff)

        # The old way: accessing .items explicitly
        accessed_items = artefact.items

        assert len(accessed_items) == 2
        assert accessed_items[0].text == "Item 1"

    def test_metadata_access_still_works(self) -> None:
        """Verify that metadata access is not affected by iteration changes."""
        items = [TextContent(text="Item")]
        stuff = _make_list_stuff(items)
        artefact = StuffArtefact(stuff)

        assert artefact["_stuff_name"] == "test_list"
        assert artefact["_stuff_code"] == "test_list"
        assert artefact["_content_class"] == "ListContent"

    def test_truthiness_of_present_singular_value(self) -> None:
        """A present non-list artefact is truthy — Jinja2's `{% if var %}` guard (the optionals
        guard idiom) must never crash on a present value via the __len__ fallback.
        """
        artefact = StuffArtefact(_make_text_stuff("Plain text"))

        assert bool(artefact) is True

    def test_truthiness_of_list_follows_emptiness(self) -> None:
        """A ListContent artefact follows list emptiness (D4: [] is the absence story for plurals)."""
        assert bool(StuffArtefact(_make_list_stuff([TextContent(text="Item")]))) is True
        assert bool(StuffArtefact(_make_list_stuff([]))) is False
