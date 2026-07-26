import datetime
import json
from typing import Any, cast

import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.runtime_bridge.primitives.hydration import (
    _hydrate_list_item,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    hydrate_working_memory,
)
from pipelex.service_hub import get_class_registry


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


def _make_yes_no_concept() -> Concept:
    """Build a native YesNo concept for testing."""
    return Concept(
        code="YesNo",
        domain_code=SpecialDomain.NATIVE,
        description="The answer to a yes/no question",
        structure_class_name="YesNoContent",
    )


def _make_date_concept() -> Concept:
    """Build a native Date concept for testing."""
    return Concept(
        code="Date",
        domain_code=SpecialDomain.NATIVE,
        description="A calendar date, optionally with a time of day — as precise as its source states.",
        structure_class_name="DateContent",
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
        if not registry.has_class(name="YesNoContent"):
            registry.register_class(YesNoContent)
        if not registry.has_class(name="DateContent"):
            registry.register_class(DateContent)

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

    def test_hydrate_with_yes_no(self) -> None:
        """A YesNo stuff survives the dump/hydrate round-trip as typed YesNoContent.

        Cheap insurance against the distributed decode failure mode: a content class that
        fails payload decode inside a Temporal workflow retries forever (a hang, not an error).
        """
        working_memory = WorkingMemory()
        working_memory.root["verdict"] = Stuff(
            stuff_code="test",
            stuff_name="verdict",
            concept=_make_yes_no_concept(),
            content=YesNoContent(yes_no=True),
        )

        raw = working_memory.dump_for_transport()
        hydrated = hydrate_working_memory(raw)

        stuff = hydrated.root["verdict"]
        assert isinstance(stuff.content, YesNoContent)
        assert stuff.content.yes_no is True

    def test_hydrate_yes_no_in_list(self) -> None:
        """A ListContent of YesNoContent survives the dump/hydrate round-trip."""
        working_memory = WorkingMemory()
        working_memory.root["verdicts"] = Stuff(
            stuff_code="test",
            stuff_name="verdicts",
            concept=_make_yes_no_concept(),
            content=ListContent(items=[YesNoContent(yes_no=True), YesNoContent(yes_no=False)]),
        )

        raw = working_memory.dump_for_transport()
        hydrated = hydrate_working_memory(raw)

        content = hydrated.root["verdicts"].content
        assert isinstance(content, ListContent)
        list_content = cast("ListContent[YesNoContent]", content)
        assert [item.yes_no for item in list_content.items] == [True, False]

    def test_hydrate_date_with_offset_preserved(self) -> None:
        """A Date stuff with an offset-carrying time survives the transport round-trip, offset intact.

        Transport dumps in pydantic python mode, so real date/time objects sit in the dict; hydration
        goes back through model_validate (the kajson road). A decode failure here would hang a workflow.
        """
        working_memory = WorkingMemory()
        offset = datetime.timezone(datetime.timedelta(hours=2))
        working_memory.root["departure"] = Stuff(
            stuff_code="test",
            stuff_name="departure",
            concept=_make_date_concept(),
            content=DateContent(date=datetime.date(2026, 7, 7), time=datetime.time(15, 40, tzinfo=offset)),
        )

        hydrated = hydrate_working_memory(working_memory.dump_for_transport())

        stuff = hydrated.root["departure"]
        assert isinstance(stuff.content, DateContent)
        assert stuff.content.date == datetime.date(2026, 7, 7)
        assert stuff.content.time is not None
        assert stuff.content.time.utcoffset() == datetime.timedelta(hours=2)

    def test_hydrate_date_in_list(self) -> None:
        """A ListContent of DateContent survives the round-trip via the __pipelex_class__ marker path."""
        working_memory = WorkingMemory()
        working_memory.root["dates"] = Stuff(
            stuff_code="test",
            stuff_name="dates",
            concept=_make_date_concept(),
            content=ListContent(
                items=[
                    DateContent(date=datetime.date(2026, 7, 7)),
                    DateContent(date=datetime.date(2026, 8, 6), time=datetime.time(9, 0)),
                ]
            ),
        )

        hydrated = hydrate_working_memory(working_memory.dump_for_transport())

        content = hydrated.root["dates"].content
        assert isinstance(content, ListContent)
        list_content = cast("ListContent[DateContent]", content)
        assert [item.date for item in list_content.items] == [datetime.date(2026, 7, 7), datetime.date(2026, 8, 6)]
        assert list_content.items[0].time is None
        assert list_content.items[1].time == datetime.time(9, 0)

    def test_hydrate_date_from_iso_string_wire(self) -> None:
        """The ISO-string road: a json-mode transport dict (dates/times become ISO strings, as a
        non-kajson wire such as pydantic json-mode or a FastAPI encoder delivers them) must still
        hydrate — model_validate parses the ISO strings back to typed objects, offset preserved.
        """
        working_memory = WorkingMemory()
        offset = datetime.timezone(datetime.timedelta(hours=2))
        working_memory.root["departure"] = Stuff(
            stuff_code="test",
            stuff_name="departure",
            concept=_make_date_concept(),
            content=DateContent(date=datetime.date(2026, 7, 7), time=datetime.time(15, 40, tzinfo=offset)),
        )

        # Force every value through JSON so real date/time objects become ISO strings on the wire.
        raw = json.loads(json.dumps(working_memory.dump_for_transport(), default=str))
        hydrated = hydrate_working_memory(raw)

        stuff = hydrated.root["departure"]
        assert isinstance(stuff.content, DateContent)
        assert stuff.content.date == datetime.date(2026, 7, 7)
        assert stuff.content.time is not None
        assert stuff.content.time.utcoffset() == datetime.timedelta(hours=2)

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

    def test_hydrate_round_trips_absence_ledger(self) -> None:
        """The absence ledger survives the dump_for_transport → hydrate round-trip: a recorded
        absence must not degrade to a hard miss after cross-process transit.
        """
        working_memory = WorkingMemory()
        working_memory.root["kept"] = _make_text_stuff("kept", "still here")
        origin = AbsenceRecord(
            variable_name="source",
            kind=AbsenceKind.NOT_PROVIDED,
            reason="optional input 'source' was not provided by the caller",
        )
        chained = AbsenceRecord(
            variable_name="analysis",
            kind=AbsenceKind.SKIPPED,
            reason="skipped because input 'source' is absent",
            producing_pipe="analyze",
            upstream=origin,
        )
        working_memory.record_absence(origin)
        working_memory.record_resolved_absence(chained)

        hydrated = hydrate_working_memory(working_memory.dump_for_transport())

        assert hydrated.absences["source"] == origin
        assert hydrated.absences["analysis"] == chained
        assert hydrated.absences["analysis"].upstream == origin
        assert hydrated.root["kept"].content == TextContent(text="still here")

    def test_hydrate_raises_on_malformed_absence_record(self) -> None:
        """A malformed ledger entry fails hydration loudly — never a silently dropped record."""
        raw: dict[str, Any] = {
            "root": {},
            "aliases": {},
            "absences": {"broken": {"kind": "not_a_kind"}},
        }

        with pytest.raises(PipeJobError, match="broken"):
            hydrate_working_memory(raw)
