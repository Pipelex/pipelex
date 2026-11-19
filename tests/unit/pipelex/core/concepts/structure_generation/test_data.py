from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any, ClassVar, NamedTuple

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.stuffs.text_content import TextContent


def _field(**blueprint: Any) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint.model_validate({"description": "A field", **blueprint})


class ShadowingFieldCase(NamedTuple):
    """A structure whose first field is named like a module-level name, and a payload of its fields with their values.

    The second field, `after`, has the type that name spells, so the case pins both the field's own annotation and the
    field after it.
    """

    shadowed_name: str
    structure: dict[str, ConceptStructureBlueprint]
    payload: dict[str, Any]
    expected_values: dict[str, Any]


class ShadowingFieldNamesTestData:
    # Names a class written as source would read at module level for its annotations and defaults.
    READ_NAME_CASES: ClassVar[list[ShadowingFieldCase]] = [
        ShadowingFieldCase(
            shadowed_name="date",
            structure={"date": _field(type="date", required=True), "after": _field(type="date", required=True)},
            payload={"date": "2026-09-27", "after": "2026-09-28"},
            expected_values={"date": date(2026, 9, 27), "after": date(2026, 9, 28)},
        ),
        ShadowingFieldCase(
            shadowed_name="datetime",
            structure={"datetime": _field(type="datetime", required=True), "after": _field(type="datetime", required=True)},
            payload={"datetime": "2026-09-27T10:30:00+02:00", "after": "2026-09-28T08:00:00+00:00"},
            expected_values={
                "datetime": datetime(2026, 9, 27, 10, 30, tzinfo=timezone(timedelta(hours=2))),
                "after": datetime(2026, 9, 28, 8, 0, tzinfo=UTC),
            },
        ),
        ShadowingFieldCase(
            shadowed_name="time",
            structure={"time": _field(type="time", required=True), "after": _field(type="time", required=True)},
            payload={"time": "10:30:00", "after": "23:59:59"},
            expected_values={"time": time(10, 30), "after": time(23, 59, 59)},
        ),
        ShadowingFieldCase(
            shadowed_name="str",
            structure={"str": _field(type="text", required=True), "after": _field(type="text", required=True)},
            payload={"str": "first", "after": "second"},
            expected_values={"str": "first", "after": "second"},
        ),
        ShadowingFieldCase(
            shadowed_name="int",
            structure={"int": _field(type="integer", required=True), "after": _field(type="integer", required=True)},
            payload={"int": 3, "after": 4},
            expected_values={"int": 3, "after": 4},
        ),
        ShadowingFieldCase(
            shadowed_name="float",
            structure={"float": _field(type="number", required=True), "after": _field(type="number", required=True)},
            payload={"float": 1.5, "after": 2.5},
            expected_values={"float": 1.5, "after": 2.5},
        ),
        ShadowingFieldCase(
            shadowed_name="bool",
            structure={"bool": _field(type="boolean", required=True), "after": _field(type="boolean", required=True)},
            payload={"bool": True, "after": False},
            expected_values={"bool": True, "after": False},
        ),
        ShadowingFieldCase(
            shadowed_name="list",
            structure={
                "list": _field(type="list", item_type="text", required=True),
                "after": _field(type="list", item_type="integer", required=True),
            },
            payload={"list": ["one", "two"], "after": [1, 2]},
            expected_values={"list": ["one", "two"], "after": [1, 2]},
        ),
        ShadowingFieldCase(
            shadowed_name="dict",
            structure={
                "dict": _field(type="dict", key_type="text", value_type="text", required=True),
                "after": _field(type="dict", key_type="text", value_type="integer", required=True),
            },
            payload={"dict": {"key": "value"}, "after": {"count": 2}},
            expected_values={"dict": {"key": "value"}, "after": {"count": 2}},
        ),
        ShadowingFieldCase(
            shadowed_name="Literal",
            structure={"Literal": _field(choices=["red", "green"], required=True), "after": _field(choices=["small", "large"], required=True)},
            payload={"Literal": "red", "after": "large"},
            expected_values={"Literal": "red", "after": "large"},
        ),
        ShadowingFieldCase(
            shadowed_name="Field",
            structure={"Field": _field(type="text", required=True), "after": _field(type="text", required=True)},
            payload={"Field": "first", "after": "second"},
            expected_values={"Field": "first", "after": "second"},
        ),
        ShadowingFieldCase(
            shadowed_name="Any",
            structure={"Any": _field(type="concept", concept_ref="native.Anything"), "after": _field(type="concept", concept_ref="native.Anything")},
            payload={"Any": {"loose": [1, "two"]}, "after": 3},
            expected_values={"Any": {"loose": [1, "two"]}, "after": 3},
        ),
        ShadowingFieldCase(
            shadowed_name="NonNullAny",
            structure={
                "NonNullAny": _field(type="concept", concept_ref="native.Anything", required=True),
                "after": _field(type="concept", concept_ref="native.Anything", required=True),
            },
            payload={"NonNullAny": "anything", "after": [1, 2]},
            expected_values={"NonNullAny": "anything", "after": [1, 2]},
        ),
        ShadowingFieldCase(
            shadowed_name="TextContent",
            structure={
                "TextContent": _field(type="concept", concept_ref="native.Text", required=True),
                "after": _field(type="concept", concept_ref="native.Text", required=True),
            },
            payload={"TextContent": {"text": "first"}, "after": {"text": "second"}},
            expected_values={"TextContent": TextContent(text="first"), "after": TextContent(text="second")},
        ),
    ]

    # Names a module written as source would import, or could, which its class body never reads.
    UNREAD_NAME_CASES: ClassVar[list[ShadowingFieldCase]] = [
        ShadowingFieldCase(
            shadowed_name=unread_name,
            structure={unread_name: _field(type="text", required=True), "after": _field(type="text", required=True)},
            payload={unread_name: "first", "after": "second"},
            expected_values={unread_name: "first", "after": "second"},
        )
        for unread_name in ("StructuredContent", "Enum", "BaseModel", "List", "Optional", "Annotated", "Union")
    ]

    # Fields named like the temporal type they hold, each with a default of that type.
    TEMPORAL_DEFAULTS_STRUCTURE: ClassVar[dict[str, ConceptStructureBlueprint]] = {
        "date": _field(type="date", default_value=date(2026, 7, 7)),
        "datetime": _field(type="datetime", default_value=datetime(2026, 7, 7, 15, 40, tzinfo=timezone(timedelta(hours=2)))),
        "time": _field(type="time", default_value=time(15, 40)),
    }
    TEMPORAL_DEFAULTS: ClassVar[dict[str, Any]] = {
        "date": date(2026, 7, 7),
        "datetime": datetime(2026, 7, 7, 15, 40, tzinfo=timezone(timedelta(hours=2))),
        "time": time(15, 40),
    }

    # A field named like the class of the concept a field of the structure refers to, which no alias can stand for.
    FORWARD_REF_DOMAIN: ClassVar[str] = "shadow_domain"
    FORWARD_REF_FINDING: ClassVar[str] = (
        "its field 'shadow_domain__Person' has the name of the Python class of the concept 'shadow_domain.Person', which the structure refers to"
    )
    FORWARD_REF_STRUCTURES: ClassVar[list[tuple[str, dict[str, ConceptStructureBlueprint]]]] = [
        (
            "the field refers to the class it is named like",
            {"shadow_domain__Person": _field(type="concept", concept_ref="Person", required=True)},
        ),
        (
            "another field refers to the class it is named like",
            {
                "shadow_domain__Person": _field(type="text", required=True),
                "owner": _field(type="list", item_type="concept", item_concept_ref="shadow_domain.Person", required=True),
            },
        ),
    ]


def _concept(description: str, **fields: ConceptStructureBlueprint) -> ConceptBlueprint:
    return ConceptBlueprint(description=description, structure=dict(fields))


class StructureParityTestData:
    """Concepts with a structure, read by the runtime structure generator and by the `python-structures` emitter alike.

    Together they cover every resolved type kind, presence both ways, defaults of every kind, choices, native content
    classes, references within a domain and across domains, a class referring to itself and two classes referring to
    each other, and descriptions whose docstring a naive rendering would change. A field naming `native.Anything` is
    left out: the emitter writes it as `StructuredContent` where the runtime holds any value (L-261119-cb6979).
    """

    CONCEPTS: ClassVar[dict[str, ConceptBlueprint]] = {
        "parity.Scalars": _concept(
            "Every scalar field type, required, optional and defaulted",
            title=_field(type="text", required=True),
            ratio=_field(type="number", required=True),
            count=_field(type="integer"),
            enabled=_field(type="boolean", default_value=False),
            published_on=_field(type="date", default_value=date(2026, 7, 7)),
            recorded_at=_field(type="datetime", default_value=datetime(2026, 7, 7, 15, 40, tzinfo=timezone(timedelta(hours=2)))),
            starts_at=_field(type="time", default_value=time(9, 30)),
            note=_field(type="text", default_value="none"),
        ),
        "parity.Choices": _concept(
            "Choices, required, optional and defaulted",
            status=_field(choices=["draft", "final"], required=True),
            tier=_field(choices=["low", "medium", "high"], default_value="medium"),
            verdict=_field(choices=['marked "urgent"', "left, unmarked"]),
        ),
        "parity.Containers": _concept(
            "Lists and dicts, typed and untyped, with defaults",
            tags=_field(type="list", item_type="text", required=True),
            scores=_field(type="list", item_type="number", default_value=[1.5, 2.5]),
            deadlines=_field(type="list", item_type="date"),
            counts=_field(type="dict", key_type="text", value_type="integer", default_value={"total": 12, "per-reviewer": 3}),
            labels=_field(type="dict", key_type="text", value_type="text"),
            loose=_field(type="list", required=True),
        ),
        "parity.Natives": _concept(
            "Native content classes as fields and list items",
            picture=_field(type="concept", concept_ref="native.Image", required=True),
            gallery=_field(type="list", item_type="concept", item_concept_ref="native.Image"),
            caption=_field(type="concept", concept_ref="Text"),
            page=_field(type="concept", concept_ref="native.Html"),
        ),
        "parity.Node": _concept(
            "A tree node, referring to its own class",
            label=_field(type="text", required=True),
            children=_field(type="list", item_type="concept", item_concept_ref="parity.Node"),
            parent=_field(type="concept", concept_ref="Node"),
        ),
        "parity.Author": _concept(
            "An author, referring to the books that refer back to it",
            name=_field(type="text", required=True),
            books=_field(type="list", item_type="concept", item_concept_ref="Book", required=True),
        ),
        "parity.Book": _concept(
            "A book, referring to its author",
            title=_field(type="text", required=True),
            author=_field(type="concept", concept_ref="parity.Author"),
            shelf=_field(type="concept", concept_ref="library.Shelf", required=True),
        ),
        "library.Shelf": _concept(
            "A shelf in another domain, referring back to the books on it",
            code=_field(type="text", required=True),
            books=_field(type="list", item_type="concept", item_concept_ref="parity.Book"),
        ),
        "parity.Described": _concept(
            "\n  Intro:\n    - item one\n    - item two\n",
            notes=_field(
                type="text",
                description='A "quoted" word, a \\ backslash,\n\ta tab and trailing spaces   ' + "and a long tail " * 12,
                required=True,
            ),
        ),
        "parity.Spanning": _concept(
            'A description that spans lines.\n\nIts second paragraph holds """ triple quotes.',
            padded=_field(type="text", description="  Padded with edge whitespace  "),
        ),
    }
