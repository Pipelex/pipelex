from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import IntEnum
from typing import Annotated, Any, ClassVar, Literal
from uuid import UUID

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, HttpUrl, create_model

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


def _object(**properties: Any) -> dict[str, Any]:
    return {"title": "Refused", "type": "object", "properties": properties}


class _Inner(BaseModel):
    """A nested model with its own description."""

    value: int = Field(ge=0)


class _AllShapes(StructuredContent):
    """Every shape the rebuild supports, in one class.

    The second paragraph keeps its line.
    """

    text: str = Field(description="A text", min_length=1, max_length=40, pattern=r"^\w+$")
    count: int = Field(default=3, gt=0, lt=100, multiple_of=3)
    ratio: float | None = Field(default=None, ge=0, le=1)
    flag: bool = False
    when: date
    at: datetime | None = None
    clock: time | None = None
    link: AnyUrl | None = None
    web: HttpUrl | None = None
    kind: Literal["a", "b"] = "a"
    fixed: Literal["only"] = "only"
    tags: list[str] = Field(default_factory=list, min_length=0, max_length=5)
    unique: set[int] = Field(default_factory=set[int])
    scores: dict[str, float] = Field(default_factory=dict)
    blob: dict[str, Any] | None = None
    anything: Any = None
    inner: _Inner
    inners: list[_Inner] | None = None
    examples_field: str = Field(default="x", examples=["x", "y"])


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class _Recursive(BaseModel):
    name: str
    parent: "_Recursive | None" = None


class Counter(BaseModel):
    """A nested model whose every field has a default."""

    count: int = 1


class Rank(IntEnum):
    FIRST = 1
    SECOND = 2


def _default_names() -> list[str]:
    return ["ok"]


class AliasedProperties(StructuredContent):
    """Properties no field can be named after, a keyword, names that are no identifier and one led by an underscore."""

    origin: str = Field(alias="from")
    first_name: str = Field(alias="first-name")
    kind: str = Field(alias="@type")
    identifier: str | None = Field(default=None, alias="_id")
    field_0: str = Field(description="A property named as the builder would name an aliased field")


class FactoryDefaults(StructuredContent):
    """Fields with a default factory, which the schema shows as optional with no default."""

    label: str
    counter: Counter = Field(default_factory=Counter)
    names: list[str] = Field(default_factory=_default_names, min_length=1)
    tags: list[str] = Field(default_factory=list)


class Decimals(StructuredContent):
    """Decimals, bare, optional, constrained, in a list and defaulted."""

    amount: Decimal
    maybe: Decimal | None = None
    price: Decimal = Field(default=Decimal("1.50"), max_digits=5, decimal_places=2)
    digits_only: Decimal = Field(default=Decimal(12), max_digits=4)
    places_only: Decimal = Field(default=Decimal("0.125"), decimal_places=3)
    bounded: Decimal = Field(default=Decimal(1), ge=0, lt=Decimal("9.5"), multiple_of=0.5)
    amounts: list[Decimal] = Field(default_factory=empty_list_factory_of(Decimal))


class Formats(StructuredContent):
    """The string formats of a UUID, of bytes and of a duration."""

    identifier: UUID
    payload: bytes
    elapsed: timedelta
    maybe_identifier: UUID | None = None


class Tuples(StructuredContent):
    """Tuples of a fixed length, nested and optional, and one of any length, which pydantic writes as an array."""

    pair: tuple[str, int]
    nested: tuple[int, tuple[str, str]] | None = None
    open_ended: tuple[str, ...] = Field(default=("a",), min_length=1)


class Cat(BaseModel):
    kind: Literal["cat"]
    lives: int


class Dog(BaseModel):
    kind: Literal["dog"]
    name: str


Pet = Annotated[Cat | Dog, Field(discriminator="kind")]


def _no_pets() -> list[Pet]:
    return []


class Pets(StructuredContent):
    """A discriminated union, bare, optional and in a list."""

    pet: Pet
    maybe_pet: Pet | None = None
    pets: list[Pet] = Field(default_factory=_no_pets)


class ModelDefaults(StructuredContent):
    """Defaults the schema writes in their JSON form: a nested model and an enumeration member."""

    counter: Counter = Counter(count=2)
    rank: Rank = Rank.SECOND


# Two definitions titled `Item`, from two modules, which pydantic keys apart in `$defs`.
_ItemOfA = create_model("Item", __module__="module_a", number=(int, ...))
_ItemOfB = create_model("Item", __module__="module_b", text=(str, ...))
SharedTitles = create_model("SharedTitles", first=(_ItemOfA, ...), second=(_ItemOfB, ...))


def _field(**blueprint: Any) -> ConceptStructureBlueprint:
    return ConceptStructureBlueprint.model_validate({"description": "A field", **blueprint})


class SchemaRebuildTestData:
    # Shapes outside the subset and names no field can take, each with a fragment its refusal names.
    REFUSED_SCHEMAS: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        ("unknown root keyword", {**_object(), "x-python-import": {"module": "os", "name": "system"}}, "x-python-import"),
        (
            "code generator extension in a definition",
            {
                **_object(hit={"$ref": "#/$defs/Run"}),
                "$defs": {"Run": {"type": "object", "properties": {}, "x-python-import": {"module": "subprocess", "name": "run"}}},
            },
            "x-python-import",
        ),
        ("code generator extension on a property", _object(x={"type": "integer", "x-python-type": "subprocess.Popen"}), "x-python-type"),
        ("non-local reference", _object(x={"$ref": "https://example.com/schema.json"}), "only a local"),
        ("reference to a nested pointer", _object(x={"$ref": "#/properties/y"}), "only a local"),
        ("dangling reference", _object(x={"$ref": "#/$defs/Missing"}), "does not define"),
        ("inline object", _object(x={"type": "object", "properties": {"y": {"type": "string"}}}), "inline object"),
        ("allOf of two members", _object(x={"allOf": [{"type": "string"}, {"type": "integer"}]}), "allOf of one member"),
        ("oneOf without a discriminator", _object(x={"oneOf": [{"type": "string"}, {"type": "integer"}]}), "only as a discriminated union"),
        (
            "discriminated union of inline members",
            _object(x={"oneOf": [{"type": "string"}], "discriminator": {"propertyName": "kind", "mapping": {"a": "#/$defs/A"}}}),
            "member of a discriminated union is a reference",
        ),
        (
            "discriminator mapping to a definition that is no member",
            {
                **_object(x={"oneOf": [{"$ref": "#/$defs/A"}], "discriminator": {"propertyName": "kind", "mapping": {"a": "#/$defs/B"}}}),
                "$defs": {"A": {"type": "object", "properties": {"kind": {"const": "a", "type": "string"}}}},
            },
            "exactly the members",
        ),
        (
            "discriminator on a keyword property",
            _object(x={"oneOf": [{"$ref": "#/$defs/A"}], "discriminator": {"propertyName": "class", "mapping": {"a": "#/$defs/A"}}}),
            "its own field name",
        ),
        ("discriminator on an anyOf", _object(x={"anyOf": [{"type": "string"}], "discriminator": {"propertyName": "kind"}}), "discriminator"),
        ("unknown string format", _object(x={"type": "string", "format": "ipv4"}), "format 'ipv4'"),
        ("unknown type", _object(x={"type": "decimal"}), "type 'decimal'"),
        ("list of types", _object(x={"type": ["string", "null"]}), "type ['string', 'null']"),
        ("tuple without a fixed length", _object(x={"type": "array", "prefixItems": [{"type": "string"}]}), "least and most items"),
        (
            "tuple with a variadic tail",
            _object(x={"type": "array", "prefixItems": [{"type": "string"}], "items": {"type": "integer"}, "minItems": 1}),
            "['items']",
        ),
        (
            "number beside a string that is no decimal's",
            _object(x={"anyOf": [{"type": "number"}, {"type": "string", "pattern": "^(?!x)[0-9]+$"}]}),
            "did not build into a class",
        ),
        ("enumeration of floats", _object(x={"enum": [1.5, 2.5]}), "strings, integers or booleans"),
        ("enumeration whose type is not its values'", _object(x={"enum": ["a"], "type": "integer"}), "declared type"),
        ("typed extra properties on an object", {**_object(), "additionalProperties": {"type": "string"}}, "never typed"),
        ("constrained dictionary keys", _object(x={"type": "object", "propertyNames": {"pattern": "^a"}}), "propertyNames"),
        ("URL without its minimum length", _object(x={"type": "string", "format": "uri"}), "at least one character"),
        ("constraint on a boolean", _object(x={"type": "boolean", "minimum": 1}), "minimum"),
        ("bound that is not a number", _object(x={"type": "integer", "minimum": "1"}), "a bound is a number"),
        ("pattern that does not compile", _object(x={"type": "string", "pattern": "("}), "did not build into a class"),
        (
            "definition that is not an object",
            {**_object(x={"$ref": "#/$defs/Str"}), "$defs": {"Str": {"type": "string"}}},
            "object or an enumeration",
        ),
        ("required name that is no property", {**_object(), "required": ["ghost"]}, "required names"),
        ("root that is no object", {"title": "Refused", "type": "string"}, "object or an enumeration"),
        ("field name of a pydantic method", _object(model_json_schema={"type": "string"}), "shadow a method"),
        ("field name of pydantic's config", _object(model_config={"type": "string"}), "shadow a method"),
    ]

    # Classes whose schema the rebuild must reproduce exactly, beside the native content classes.
    MODEL_CLASSES: ClassVar[list[type[BaseModel]]] = [
        _AllShapes,
        _Inner,
        _Open,
        _Closed,
        _Recursive,
        AliasedProperties,
        FactoryDefaults,
        Decimals,
        Formats,
        Tuples,
        Pets,
        ModelDefaults,
        SharedTitles,
    ]

    # Classes and values valid for them, which must survive the boundary's rebuild, by-alias dump and validation.
    ROUND_TRIP_CASES: ClassVar[list[tuple[type[BaseModel], dict[str, Any]]]] = [
        (AliasedProperties, {"from": "Paris", "first-name": "Ada", "@type": "Person", "_id": "p-1", "field_0": "kept"}),
        (AliasedProperties, {"from": "Paris", "first-name": "Ada", "@type": "Person", "field_0": "kept"}),
        (FactoryDefaults, {"label": "only the required field"}),
        (FactoryDefaults, {"label": "every field", "counter": {"count": 7}, "names": ["a", "b"], "tags": ["t"]}),
        (Decimals, {"amount": "12.345"}),
        (
            Decimals,
            {"amount": 3, "maybe": "0.1", "price": "999.99", "digits_only": "1234", "places_only": "1.5", "bounded": 9, "amounts": ["1", 2.5]},
        ),
        (Formats, {"identifier": "12345678-1234-5678-1234-567812345678", "payload": "bytes", "elapsed": "PT1H30M"}),
        (Tuples, {"pair": ["a", 1], "nested": [1, ["b", "c"]], "open_ended": ["x", "y"]}),
        (Tuples, {"pair": ["a", 1]}),
        (Pets, {"pet": {"kind": "cat", "lives": 9}, "maybe_pet": {"kind": "dog", "name": "Rex"}, "pets": [{"kind": "dog", "name": "Fido"}]}),
        (Pets, {"pet": {"kind": "dog", "name": "Rex"}}),
        (ModelDefaults, {}),
        (ModelDefaults, {"counter": {"count": 3}, "rank": 1}),
    ]

    # Concept structures as a method declares them, built into their classes by the concept factory.
    STRUCTURE_BLUEPRINTS: ClassVar[list[tuple[str, ConceptBlueprint]]] = [
        (
            "Invoice",
            ConceptBlueprint(
                description="An invoice\n    with an indented second line",
                structure={
                    "number": _field(type="text", required=True),
                    "total": _field(type="number", required=True),
                    "lines": _field(type="integer", default_value=1),
                    "paid": _field(type="boolean", default_value=False),
                    "issued": _field(type="date"),
                    "sent_at": _field(type="datetime"),
                    "cutoff": _field(type="time"),
                    "status": _field(type="text", choices=["draft", "sent", "paid"], required=True),
                    "notes": _field(type="list", item_type="text"),
                    "amounts": _field(type="dict", key_type="text", value_type="number"),
                    "metadata": _field(type="dict", key_type="text", value_type="Any"),
                    "logo": _field(type="concept", concept_ref="native.Image"),
                    "attachments": _field(type="list", item_type="concept", item_concept_ref="native.Document"),
                    "summary": "A plain text field described in one string",
                },
            ),
        ),
        (
            "Shadowing",
            ConceptBlueprint(
                description="Field names that shadow pydantic v1 methods",
                structure={
                    "copy": _field(type="text", required=True),
                    "dict": _field(type="list", item_type="integer"),
                    "json": _field(type="text"),
                    "schema": _field(type="text", default_value="kept"),
                    "model_year": _field(type="integer"),
                },
            ),
        ),
        ("Refined", ConceptBlueprint(description="A refinement of a native concept", refines="native.Image")),
        ("Described", ConceptBlueprint(description="A concept described only")),
    ]
