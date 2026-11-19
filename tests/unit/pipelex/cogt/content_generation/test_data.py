from datetime import date, datetime, time
from typing import Any, ClassVar, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, HttpUrl

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.stuffs.structured_content import StructuredContent


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
        ("oneOf", _object(x={"oneOf": [{"type": "string"}, {"type": "integer"}]}), "oneOf"),
        ("discriminated union", _object(x={"anyOf": [{"type": "string"}], "discriminator": {"propertyName": "kind"}}), "discriminator"),
        ("unknown string format", _object(x={"type": "string", "format": "email"}), "format 'email'"),
        ("unknown type", _object(x={"type": "decimal"}), "type 'decimal'"),
        ("list of types", _object(x={"type": ["string", "null"]}), "type ['string', 'null']"),
        ("tuple", _object(x={"type": "array", "prefixItems": [{"type": "string"}]}), "prefixItems"),
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
        ("field name that is not an identifier", _object(**{"first-name": {"type": "string"}}), "not an identifier"),
        ("field name that is a keyword", _object(**{"class": {"type": "string"}}), "Python keyword"),
        ("field name led by an underscore", _object(_secret={"type": "string"}), "underscore"),
        ("field name of a pydantic method", _object(model_json_schema={"type": "string"}), "shadow a method"),
        ("field name of pydantic's config", _object(model_config={"type": "string"}), "shadow a method"),
    ]

    # Classes whose schema the rebuild must reproduce exactly, beside the native content classes.
    MODEL_CLASSES: ClassVar[list[type[BaseModel]]] = [_AllShapes, _Inner, _Open, _Closed, _Recursive]

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
