from typing import Any, cast

import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.runtime_bridge.primitives.hydration import (
    _hydrate_list_item,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    hydrate_working_memory,
)


def _make_text_concept() -> Concept:
    """Build a native Text concept for testing."""
    return Concept(
        code="Text",
        domain_code=SpecialDomain.NATIVE,
        description="Plain text",
        structure_class_name="TextContent",
    )


def _make_text_stuff(name: str, text: str) -> Stuff:
    """Build a simple text Stuff."""
    return Stuff(
        stuff_code="test",
        stuff_name=name,
        concept=_make_text_concept(),
        content=TextContent(text=text),
    )


class TestHydrateWorkingMemory:
    @pytest.fixture(autouse=True)
    def _register_content_classes(self) -> None:
        """Ensure TextContent and NumberContent are registered for hydration tests."""
        registry = get_class_registry()
        if not registry.has_class(name="TextContent"):
            registry.register_class(TextContent)
        if not registry.has_class(name="NumberContent"):
            registry.register_class(NumberContent)

    def test_hydrate_with_native_text(self) -> None:
        """A raw dict containing TextContent stuff hydrates to typed TextContent."""
        working_memory = WorkingMemory()
        working_memory.root["greeting"] = _make_text_stuff("greeting", "Hello, world!")

        raw = working_memory.dump_for_transport()
        hydrated = hydrate_working_memory(raw)

        assert "greeting" in hydrated.root
        stuff = hydrated.root["greeting"]
        assert isinstance(stuff.content, TextContent)
        assert stuff.content.text == "Hello, world!"
        assert stuff.stuff_name == "greeting"

    def test_hydrate_empty(self) -> None:
        """An empty WorkingMemory raw dict hydrates to empty WorkingMemory."""
        working_memory = WorkingMemory()
        raw = working_memory.dump_for_transport()

        hydrated = hydrate_working_memory(raw)

        assert len(hydrated.root) == 0
        assert len(hydrated.aliases) == 0

    def test_hydrate_preserves_aliases(self) -> None:
        """Aliases survive the dump/hydrate round-trip."""
        working_memory = WorkingMemory()
        working_memory.root["greeting"] = _make_text_stuff("greeting", "Hello!")
        working_memory.aliases["main_stuff"] = "greeting"

        raw = working_memory.dump_for_transport()
        hydrated = hydrate_working_memory(raw)

        assert hydrated.aliases == {"main_stuff": "greeting"}
        assert "greeting" in hydrated.root

    def test_hydrate_list_content_round_trip(self) -> None:
        """ListContent survives dump_for_transport/hydrate round-trip as a plain list."""
        working_memory = WorkingMemory()
        list_stuff = Stuff(
            stuff_code="test",
            stuff_name="colors",
            concept=_make_text_concept(),
            content=ListContent(
                items=[
                    TextContent(text="blue"),
                    TextContent(text="red"),
                    TextContent(text="green"),
                ]
            ),
        )
        working_memory.root["colors"] = list_stuff

        raw = working_memory.dump_for_transport()

        # Verify the Temporal format uses a plain list, not {"items": [...]}
        assert isinstance(raw["root"]["colors"]["content"], list)

        # Per-item type markers must use the pipelex-private namespace and must NOT
        # use kajson's __class__/__module__ keys — the rename is what prevents
        # kajson's universal decoder from trying to eagerly resolve the class
        # during Temporal payload conversion.
        for item_dict in cast("list[dict[str, Any]]", raw["root"]["colors"]["content"]):
            assert "__class__" not in item_dict
            assert "__module__" not in item_dict
            assert item_dict["__pipelex_class__"] == "TextContent"

        hydrated = hydrate_working_memory(raw)

        assert "colors" in hydrated.root
        stuff = hydrated.root["colors"]
        content = stuff.content
        assert isinstance(content, ListContent)
        list_content = cast("ListContent[TextContent]", content)
        assert len(list_content.items) == 3
        assert all(isinstance(item, TextContent) for item in list_content.items)
        assert list_content.items[0].text == "blue"
        assert list_content.items[1].text == "red"
        assert list_content.items[2].text == "green"

    def test_dump_for_transport_list_items_carry_pipelex_markers_only(self) -> None:
        """dump_for_transport must emit pipelex-private type markers, never kajson's __class__/__module__.

        This is the structural guard against the cross-process decode bug: if these
        items carried __class__ keys, kajson's universal decoder would try to bind
        the class at the Temporal data-converter boundary, before pipelex's
        per-workflow ClassRegistry is loaded.
        """
        working_memory = WorkingMemory()
        list_stuff = Stuff(
            stuff_code="test",
            stuff_name="items",
            concept=_make_text_concept(),
            content=ListContent(items=[TextContent(text="one"), TextContent(text="two")]),
        )
        working_memory.root["items"] = list_stuff

        raw = working_memory.dump_for_transport()

        serialized_items = cast("list[dict[str, Any]]", raw["root"]["items"]["content"])
        assert isinstance(serialized_items, list)
        assert len(serialized_items) == 2
        for item_dict in serialized_items:
            assert "__class__" not in item_dict
            assert "__module__" not in item_dict
            assert item_dict["__pipelex_class__"] == "TextContent"
            assert item_dict["__pipelex_module__"] == "pipelex.core.stuffs.text_content"

    def test_hydrate_list_item_reads_pipelex_markers(self) -> None:
        """_hydrate_list_item must resolve the per-item class from __pipelex_class__.

        Uses NumberContent (no 'text' field) so the legacy text-fallback path at
        the bottom of _hydrate_list_item cannot accidentally satisfy the test —
        the only way to return a NumberContent here is via the marker lookup.
        """
        raw_item = {
            "number": 42,
            "__pipelex_class__": "NumberContent",
            "__pipelex_module__": "pipelex.core.stuffs.number_content",
        }

        result = _hydrate_list_item(raw_item)

        assert isinstance(result, NumberContent)
        assert result.number == 42

    def test_hydrate_raises_on_missing_registry_class(self) -> None:
        """Hydration raises PipeJobError when the concept's structure_class_name is not in the registry."""
        raw = {
            "root": {
                "bad_stuff": {
                    "stuff_code": "test",
                    "stuff_name": "bad_stuff",
                    "concept": {
                        "code": "NonExistent",
                        "domain_code": "native",
                        "description": "Missing class",
                        "structure_class_name": "NonExistentContent",
                    },
                    "content": {"text": "hello"},
                },
            },
            "aliases": {},
        }

        with pytest.raises(PipeJobError, match="bad_stuff"):
            hydrate_working_memory(raw)

    def test_hydrate_raises_on_validation_error(self) -> None:
        """Hydration raises PipeJobError when content doesn't match the expected schema."""
        raw = {
            "root": {
                "invalid_stuff": {
                    "stuff_code": "test",
                    "stuff_name": "invalid_stuff",
                    "concept": {
                        "code": "Text",
                        "domain_code": "native",
                        "description": "Plain text",
                        "structure_class_name": "TextContent",
                    },
                    "content": {"completely_wrong_field": 42},
                },
            },
            "aliases": {},
        }

        with pytest.raises(PipeJobError, match="invalid_stuff"):
            hydrate_working_memory(raw)
