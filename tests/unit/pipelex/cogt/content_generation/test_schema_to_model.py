"""Unit tests for SchemaToModelFactory: rebuilding BaseModel classes from JSON schemas with create_model."""

import copy
import importlib.util
import threading
import uuid
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, get_args, get_origin

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, Field, ValidationError
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.exceptions import UnsupportedSchemaError
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory, _SchemaModelBuilder  # pyright: ignore[reportPrivateUsage]
from pipelex.system.registries.class_registry_access import get_class_registry
from tests.unit.pipelex.cogt.content_generation.test_data import (
    AliasedProperties,
    BoundedDicts,
    Decimals,
    DeprecatedFields,
    FactoryDefaults,
    ModelChain,
    ModelDefaults,
    MoreFormats,
    NestedModelDefaults,
    Pets,
    RingEnd,
    SchemaRebuildTestData,
    SharedTitles,
    TitledTypes,
    Tuples,
    UnvalidatedDefaults,
)


class SimpleModel(BaseModel):
    name: str = Field(description="The name")
    age: int = Field(description="The age")


class ModelWithLiteralChoices(BaseModel):
    """A model whose ``recommendation`` field is a ``Literal`` over string choices, as a ``choices`` declaration makes."""

    recommendation: Literal["Strong Match", "Good Match", "Partial Match", "Poor Match"]


class ModelWithJsonObject(BaseModel):
    """A model with a free-form JSON object field, as ``JSONContent`` carries."""

    json_obj: dict[str, Any] = Field(description="The JSON object")


class ModelWithConstraints(BaseModel):
    score: float = Field(gt=0, le=10)
    code: str = Field(min_length=2, max_length=4, pattern=r"^[A-Z]+$")
    tags: list[str] = Field(min_length=1)
    ratio: float | None = Field(default=None, ge=0, le=1)


class Address(BaseModel):
    street: str
    city: str


class PersonWithAddress(BaseModel):
    name: str
    address: Address


class TreeNode(BaseModel):
    label: str
    children: list["TreeNode"] | None = None


class Tone(StrEnum):
    FORMAL = "formal"
    CASUAL = "casual"


class ModelWithEnum(BaseModel):
    tone: Tone


class ModelWithIndentedDescription(BaseModel):
    # Assigned rather than written as a docstring, which the formatter would reflow.
    __doc__ = "\n    Indented first line.\nThen a line that is not.\n"

    note: str


class ModelWithPresenceVariants(BaseModel):
    """A defaulted field, a field that may hold nothing, and a required one."""

    note: str = Field(default="fallback", description="A defaulted note")
    remark: str | None = Field(default=None, description="An optional remark")
    title: str = Field(..., description="A required title")


def _unique_schema(model_class: type[BaseModel]) -> tuple[dict[str, Any], str]:
    """The class's schema under a title no other test uses, so the class-level cache never answers for it."""
    schema = model_class.model_json_schema()
    title = f"{model_class.__name__}_{uuid.uuid4().hex}"
    schema["title"] = title
    return schema, title


class TestSchemaToModel:
    def test_literal_choices_field_holds_the_value(self) -> None:
        """A ``Literal`` field rebuilds as a ``Literal`` over the same values, and a valid answer holds the value itself."""
        schema, title = _unique_schema(ModelWithLiteralChoices)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        annotation = result_class.model_fields["recommendation"].annotation
        assert get_origin(annotation) is Literal
        assert get_args(annotation) == ("Strong Match", "Good Match", "Partial Match", "Poor Match")
        assert result_class.model_validate({"recommendation": "Poor Match"}).recommendation == "Poor Match"  # type: ignore[attr-defined]
        with pytest.raises(ValidationError):
            result_class.model_validate({"recommendation": "Recommendation.Poor_Match"})
        assert result_class.model_json_schema() == schema

    def test_json_object_field_reconstructs(self) -> None:
        """A ``dict[str, Any]`` field rebuilds as one and holds any JSON object."""
        schema, title = _unique_schema(ModelWithJsonObject)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_fields["json_obj"].annotation == dict[str, Any]
        instance = result_class(json_obj={"category": "vectors", "count": 3})
        assert instance.json_obj == {"category": "vectors", "count": 3}  # type: ignore[attr-defined]

    def test_constraints_survive_the_rebuild(self) -> None:
        """Every constraint of the original class constrains the rebuilt one, inside a union too."""
        schema, title = _unique_schema(ModelWithConstraints)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        valid = {"score": 10, "code": "AB", "tags": ["x"], "ratio": 0.5}
        assert result_class.model_validate(valid).model_dump() == {**valid, "score": 10.0}
        invalid_cases: list[dict[str, Any]] = [{"score": 0}, {"code": "A"}, {"code": "ab"}, {"code": "ABCDE"}, {"tags": []}, {"ratio": 2}]
        for invalid_values in invalid_cases:
            with pytest.raises(ValidationError):
                result_class.model_validate({**valid, **invalid_values})

    def test_simple_model_reconstruction(self) -> None:
        """A simple model rebuilds under its title, with its fields, and validates data."""
        schema = SimpleModel.model_json_schema()
        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="SimpleModel")

        assert result_class.__name__ == "SimpleModel"
        assert result_class.__module__ == "builtins"
        assert list(result_class.model_fields) == ["name", "age"]
        instance = result_class(name="Alice", age=30)
        assert instance.model_dump() == {"name": "Alice", "age": 30}
        restored = result_class.model_validate_json(instance.model_dump_json())
        assert restored.model_dump() == {"name": "Alice", "age": 30}

    def test_the_rebuilt_class_is_always_a_new_one(self) -> None:
        """The title names the class, but never selects a class that already exists, in the registry or anywhere."""
        schema = SimpleModel.model_json_schema()
        schema["title"] = "TextContent"

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="TextContent")

        assert result_class is not get_class_registry().get_required_class("TextContent")
        assert result_class.__name__ == "TextContent"
        assert result_class.__bases__ == (BaseModel,)

    def test_class_name_names_a_root_without_title(self) -> None:
        """A root schema without a title takes the class name the caller gives."""
        schema = SimpleModel.model_json_schema()
        del schema["title"]
        class_name = f"Untitled_{uuid.uuid4().hex}"

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=class_name)

        assert result_class.__name__ == class_name

    def test_reconstructed_model_keeps_each_field_nullable_only_where_the_source_is(self) -> None:
        """A defaulted field refuses `null` on the rebuilt class, as on the class it was rebuilt from."""
        schema = ModelWithPresenceVariants.model_json_schema()
        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="ModelWithPresenceVariants")

        instance = result_class.model_validate({"title": "Kept"})
        assert instance.note == "fallback"  # type: ignore[attr-defined]
        assert instance.remark is None  # type: ignore[attr-defined]
        assert result_class.model_validate({"title": "Kept", "remark": None}).remark is None  # type: ignore[attr-defined]
        with pytest.raises(ValidationError) as exc_info:
            result_class.model_validate({"title": "Kept", "note": None})
        assert [error["loc"] for error in exc_info.value.errors()] == [("note",)]

    def test_a_field_with_a_default_factory_is_left_out_of_every_dump(self) -> None:
        """A field the schema shows as optional with no default is left out of every dump while the input leaves it out."""
        schema, title = _unique_schema(FactoryDefaults)
        assert set(schema["required"]) == {"label"}

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        omitted = result_class.model_validate({"label": "x"})
        assert omitted.model_dump() == {"label": "x"}
        assert omitted.model_dump(mode="json", by_alias=True, serialize_as_any=True) == {"label": "x"}
        assert omitted.model_dump_json() == '{"label":"x"}'
        assert copy.deepcopy(omitted).model_dump() == {"label": "x"}
        assert omitted.model_copy(deep=True).model_dump() == {"label": "x"}
        given = result_class.model_validate({"label": "x", "tags": [], "names": ["a"]})
        assert given.model_dump() == {"label": "x", "names": ["a"], "tags": []}
        assert FactoryDefaults.model_validate(omitted.model_dump(by_alias=True)) == FactoryDefaults(label="x")

    def test_a_property_that_cannot_name_a_field_is_an_alias(self) -> None:
        """A keyword, a name that is no identifier and an underscore-led one each name a field the builder picks, as its alias."""
        schema, title = _unique_schema(AliasedProperties)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        aliases = {field_name: field_info.alias for field_name, field_info in result_class.model_fields.items()}
        assert aliases == {"field_1": "from", "field_2": "first-name", "field_3": "@type", "field_4": "_id", "field_0": None}
        values = {"from": "Paris", "first-name": "Ada", "@type": "Person", "_id": "p-1", "field_0": "kept"}
        assert result_class.model_validate(values).model_dump(by_alias=True) == values

    def test_a_decimal_rebuilds_as_a_decimal_with_its_constraints(self) -> None:
        """The number-or-digits pair pydantic writes for a Decimal rebuilds as a Decimal, its digits and bounds enforced."""
        schema, title = _unique_schema(Decimals)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        instance = result_class.model_validate({"amount": "12.345", "maybe": 1})
        assert instance.amount == Decimal("12.345")  # type: ignore[attr-defined]
        assert type(instance.amount) is Decimal  # type: ignore[attr-defined]
        assert type(instance.maybe) is Decimal  # type: ignore[attr-defined]
        assert instance.price == Decimal("1.50")  # type: ignore[attr-defined]
        invalid_cases: list[dict[str, Any]] = [{"price": "1000"}, {"price": "1.234"}, {"digits_only": "12345"}, {"bounded": 10}, {"bounded": "0.3"}]
        for invalid_values in invalid_cases:
            with pytest.raises(ValidationError):
                result_class.model_validate({"amount": 1, **invalid_values})

    def test_a_tuple_rebuilds_as_a_tuple(self) -> None:
        """Items of a fixed length rebuild as a tuple of their types, and a tuple of any length as a list."""
        schema, title = _unique_schema(Tuples)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        instance = result_class.model_validate({"pair": ["a", "1"], "nested": [1, ["b", "c"]]})
        assert instance.pair == ("a", 1)  # type: ignore[attr-defined]
        assert instance.nested == (1, ("b", "c"))  # type: ignore[attr-defined]
        with pytest.raises(ValidationError):
            result_class.model_validate({"pair": ["a", 1, 2]})

    def test_a_discriminated_union_picks_its_member_by_the_discriminator(self) -> None:
        """A oneOf with its discriminator rebuilds as a discriminated union over the rebuilt members."""
        schema, title = _unique_schema(Pets)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        instance = result_class.model_validate({"pet": {"kind": "dog", "name": "Rex"}, "pets": [{"kind": "cat", "lives": 9}]})
        assert type(instance.pet).__name__ == "Dog"  # type: ignore[attr-defined]
        assert type(instance.pets[0]).__name__ == "Cat"  # type: ignore[attr-defined]
        with pytest.raises(ValidationError) as exc_info:
            result_class.model_validate({"pet": {"kind": "bird"}})
        assert exc_info.value.errors()[0]["type"] == "union_tag_invalid"

    def test_a_default_is_validated_into_the_field_type(self) -> None:
        """A default the schema writes in its JSON form holds the rebuilt model or enumeration member, not the raw value."""
        schema, title = _unique_schema(ModelDefaults)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        instance = result_class()
        assert type(instance.counter) is result_class.model_fields["counter"].annotation  # type: ignore[attr-defined]
        assert instance.counter.count == 2  # type: ignore[attr-defined]
        assert type(instance.rank).__name__ == "Rank"  # type: ignore[attr-defined]
        assert instance.rank == 2  # type: ignore[attr-defined]
        assert type(instance.pet).__name__ == "Cat"  # type: ignore[attr-defined]
        assert instance.pet.lives == 9  # type: ignore[attr-defined]

    def test_a_typed_default_holds_in_a_nested_class(self) -> None:
        """A class holding one whose defaults are typed validates the nested class's defaults into its types too."""
        schema, title = _unique_schema(NestedModelDefaults)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        instance = result_class.model_validate({"holder": {}})
        assert type(instance.holder.counter).__name__ == "Counter"  # type: ignore[attr-defined]
        assert type(instance.holder.rank).__name__ == "Rank"  # type: ignore[attr-defined]

    def test_a_typed_default_holds_through_a_cycle(self) -> None:
        """Classes holding one another validate each other's defaults into their types, however deep the input nests them."""
        schema = RingEnd.model_json_schema()
        assert set(schema) == {"$defs", "$ref"}

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="RingEnd")

        assert result_class.model_json_schema() == schema
        ring: Any = result_class.model_validate({"start": {"after": {"start": {"after": {}}}}})
        links: list[Any] = [ring, ring.start, ring.start.after, ring.start.after.start, ring.start.after.start.after]
        assert [type(link.counter).__name__ for link in links] == ["Counter"] * len(links)
        assert [link.counter.count for link in links] == [6, 5, 6, 5, 6]

    def test_a_default_the_original_never_validates_is_kept_as_written(self) -> None:
        """A default its own field refuses is kept raw, so an input leaving it out is accepted exactly as by the original."""
        schema, title = _unique_schema(UnvalidatedDefaults)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        original = UnvalidatedDefaults.model_validate({})
        rebuilt = result_class.model_validate({})
        assert rebuilt.model_dump() == {"count": original.count, "name": original.name} == {"count": -1, "name": None}
        with pytest.raises(ValidationError):
            result_class.model_validate({"count": -1})

    def test_bytes_and_versioned_uuids_keep_their_constraints(self) -> None:
        """Bytes keep their length bounds and each versioned UUID format refuses a UUID of another version."""
        schema, title = _unique_schema(MoreFormats)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        valid = {
            "payload": b"abc",
            "version_1": "15510910-e41c-11f1-8001-000000000001",
            "version_4": "12345678-1234-4678-9234-567812345678",
            "version_5": "886313e1-3b8a-5372-9b90-0c9aee199e5d",
        }
        assert result_class.model_validate(valid).payload == b"abc"  # type: ignore[attr-defined]
        invalid_cases: list[dict[str, Any]] = [{"payload": b""}, {"payload": b"123456789"}, {"version_4": valid["version_5"]}]
        for invalid_values in invalid_cases:
            with pytest.raises(ValidationError):
                result_class.model_validate({**valid, **invalid_values})

    def test_a_deprecated_field_stays_deprecated(self) -> None:
        """A field the schema writes as deprecated is deprecated on the rebuilt class."""
        schema, title = _unique_schema(DeprecatedFields)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        assert result_class.model_fields["legacy"].deprecated is True
        assert result_class.model_fields["current"].deprecated is None

    def test_a_title_on_a_type_that_is_no_property_is_kept(self) -> None:
        """A title pydantic writes on an item type, a reference or a union, rebuilds onto the same type."""
        schema, title = _unique_schema(TitledTypes)
        assert schema["properties"]["counters"]["items"] == {"$ref": "#/$defs/Counter", "title": "Entry"}

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        instance = result_class.model_validate({"names": ["a"], "counters": [{"count": 2}], "maybe_numbers": [None, 1]})
        assert type(instance.counters[0]).__name__ == "Counter"  # type: ignore[attr-defined]

    def test_a_dictionary_keeps_its_key_count_and_its_literal_keys(self) -> None:
        """`minProperties` and `maxProperties` bound a dictionary's keys, and `propertyNames` of strings allows only those keys."""
        schema, title = _unique_schema(BoundedDicts)

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert result_class.model_json_schema() == schema
        assert get_args(result_class.model_fields["by_kind"].annotation) == (Literal["a", "b"], int)
        valid: dict[str, Any] = {"scores": {"x": 1.0}, "by_kind": {"a": 1}}
        assert result_class.model_validate(valid).model_dump(include={"scores", "by_kind"}) == valid
        invalid_cases: list[dict[str, Any]] = [
            {"scores": {}},
            {"scores": {"a": 1, "b": 2, "c": 3, "d": 4}},
            {"by_kind": {"c": 1}},
            {"only_one": {"two": "x"}},
        ]
        for invalid_values in invalid_cases:
            with pytest.raises(ValidationError):
                result_class.model_validate({**valid, **invalid_values})

    def test_definitions_sharing_a_title_keep_their_keys(self) -> None:
        """Each definition's class is named after its `$defs` key and carries its title apart, so shared titles keep both keys."""
        schema = SharedTitles.model_json_schema()
        assert {definition["title"] for definition in schema["$defs"].values()} == {"Item"}

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="SharedTitles")

        assert result_class.model_json_schema() == schema
        first_class = result_class.model_fields["first"].annotation
        assert isinstance(first_class, type)
        assert first_class.__name__ in schema["$defs"]

    def test_an_email_rebuilds_only_where_email_validator_is_installed(self) -> None:
        """An email field needs `email-validator`, an optional dependency, without which its format is refused."""
        schema = {
            "title": f"Mail_{uuid.uuid4().hex}",
            "type": "object",
            "properties": {"to": {"format": "email", "title": "To", "type": "string"}},
            "required": ["to"],
        }
        if importlib.util.find_spec("email_validator") is None:
            with pytest.raises(UnsupportedSchemaError, match="format 'email'"):
                SchemaToModelFactory.make_from_json_schema(schema, class_name="Mail")
        else:
            assert SchemaToModelFactory.make_from_json_schema(schema, class_name="Mail").model_json_schema() == schema

    def test_nested_model_reconstruction(self) -> None:
        """A nested model rebuilds as a new class of the same name, with the same schema."""
        schema = PersonWithAddress.model_json_schema()
        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="PersonWithAddress")

        address_class = result_class.model_fields["address"].annotation
        assert isinstance(address_class, type)
        assert address_class.__name__ == "Address"
        assert address_class is not Address
        instance = result_class(name="Bob", address={"street": "123 Main", "city": "NYC"})
        assert instance.address.city == "NYC"  # type: ignore[attr-defined]
        assert result_class.model_json_schema() == schema

    def test_recursive_model_reconstruction(self) -> None:
        """A recursive model, whose schema is a root `$ref`, rebuilds through a forward reference the builder resolves."""
        schema = TreeNode.model_json_schema()
        assert set(schema) == {"$defs", "$ref"}

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="TreeNode")

        assert result_class.model_json_schema() == schema
        tree = result_class.model_validate({"label": "root", "children": [{"label": "leaf"}]})
        assert tree.children[0].label == "leaf"  # type: ignore[attr-defined]
        assert type(tree.children[0]) is result_class  # type: ignore[attr-defined]

    def test_enumeration_definition_rebuilds_as_an_enum_equal_to_its_values(self) -> None:
        """An enumeration in `$defs` rebuilds as an Enum class of that name whose members equal their values."""
        schema = ModelWithEnum.model_json_schema()

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="ModelWithEnum")

        assert result_class.model_json_schema() == schema
        tone = result_class.model_validate({"tone": "casual"}).tone  # type: ignore[attr-defined]
        assert tone == "casual"
        assert ModelWithEnum.model_validate({"tone": tone}).tone is Tone.CASUAL

    def test_description_reads_back_as_written(self) -> None:
        """A description whose first line is indented reads back unchanged, through the docstring compensation."""
        schema = ModelWithIndentedDescription.model_json_schema()
        assert schema["description"].startswith("    Indented")

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="ModelWithIndentedDescription")

        assert result_class.model_json_schema()["description"] == schema["description"]

    def test_caching_returns_same_class(self) -> None:
        """Calling with the same schema returns the same class object, and different schemas different classes."""
        class_1 = SchemaToModelFactory.make_from_json_schema(SimpleModel.model_json_schema(), class_name="SimpleModel")
        class_2 = SchemaToModelFactory.make_from_json_schema(SimpleModel.model_json_schema(), class_name="SimpleModel")
        class_nested = SchemaToModelFactory.make_from_json_schema(PersonWithAddress.model_json_schema(), class_name="PersonWithAddress")

        assert class_1 is class_2
        assert class_1 is not class_nested

    def test_the_class_name_of_a_titleless_schema_is_part_of_the_cache_key(self) -> None:
        """Two class names for one titleless schema name two classes, since the class name names the root."""
        schema = SimpleModel.model_json_schema()
        schema["description"] = f"Untitled {uuid.uuid4().hex}"
        del schema["title"]

        first_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="FirstName")
        second_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="SecondName")

        assert first_class.__name__ == "FirstName"
        assert second_class.__name__ == "SecondName"

    def test_a_cache_hit_skips_the_size_check(self, mocker: MockerFixture) -> None:
        """The size check walks the schema only on a miss, never on a hit."""
        schema, title = _unique_schema(SimpleModel)
        spy = mocker.spy(_SchemaModelBuilder, "check_size")

        SchemaToModelFactory.make_from_json_schema(schema, class_name=title)
        SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

        assert spy.call_count == 1

    def test_concurrent_first_miss_builds_only_once(self, mocker: MockerFixture) -> None:
        """N threads racing on the same uncached schema build the class exactly once."""
        schema, title = _unique_schema(SimpleModel)
        spy = mocker.spy(SchemaToModelFactory, "_build")

        thread_count = 8
        barrier = threading.Barrier(thread_count)
        results: list[type[BaseModel]] = []
        results_lock = threading.Lock()

        def worker() -> None:
            barrier.wait()
            result = SchemaToModelFactory.make_from_json_schema(schema, class_name=title)
            with results_lock:
                results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == thread_count
        assert all(result_class is results[0] for result_class in results)
        assert spy.call_count == 1

    def test_cache_bounded_size_evicts_lru(self, mocker: MockerFixture) -> None:
        """The schema cache caps at _SCHEMA_CACHE_MAX_SIZE and evicts the least recently used entry."""
        saved_cache = SchemaToModelFactory._schema_cache.copy()  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        SchemaToModelFactory._schema_cache.clear()  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        mocker.patch.object(SchemaToModelFactory, "_SCHEMA_CACHE_MAX_SIZE", 3)
        spy = mocker.spy(SchemaToModelFactory, "_build")

        try:
            schemas = [_unique_schema(SimpleModel) for _ in range(4)]
            for schema, title in schemas:
                SchemaToModelFactory.make_from_json_schema(schema, class_name=title)
                assert len(SchemaToModelFactory._schema_cache) <= 3  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            assert spy.call_count == 4

            oldest_schema, oldest_title = schemas[0]
            SchemaToModelFactory.make_from_json_schema(oldest_schema, class_name=oldest_title)
            assert spy.call_count == 5

            recent_schema, recent_title = schemas[3]
            SchemaToModelFactory.make_from_json_schema(recent_schema, class_name=recent_title)
            assert spy.call_count == 5
        finally:
            SchemaToModelFactory._schema_cache.clear()  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            SchemaToModelFactory._schema_cache.update(saved_cache)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize(("topic", "schema", "expected_fragment"), SchemaRebuildTestData.REFUSED_SCHEMAS)
    def test_a_schema_outside_the_subset_is_refused(self, topic: str, schema: dict[str, Any], expected_fragment: str) -> None:
        """Each shape outside the supported subset, and each field name no class can hold, is refused by name."""
        with pytest.raises(UnsupportedSchemaError) as exc_info:
            SchemaToModelFactory.make_from_json_schema(schema, class_name="Refused")
        assert expected_fragment in str(exc_info.value), topic
        assert exc_info.value.resolve_error_code() == CoreCode.RUNTIME_UNEXPECTED

    @pytest.mark.parametrize("field_name", ["copy", "dict", "json", "schema", "validate", "model_year"])
    def test_a_field_named_like_a_deprecated_pydantic_method_is_kept(self, field_name: str) -> None:
        """A concept structure may name a field `copy` or `json`, or start one with `model_`: the rebuilt class keeps it."""
        schema = {"title": f"Kept_{uuid.uuid4().hex}", "type": "object", "properties": {field_name: {"title": "Value", "type": "string"}}}

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="Kept")

        assert list(result_class.model_fields) == [field_name]
        assert result_class.model_validate({field_name: "kept"}).model_dump() == {field_name: "kept"}

    def test_a_schema_past_the_node_cap_is_refused(self, mocker: MockerFixture) -> None:
        """The node cap is checked before anything is built."""
        mocker.patch.object(_SchemaModelBuilder, "MAX_NODES", 20)
        schema = {"title": "Wide", "type": "object", "properties": {f"field_{index}": {"type": "string"} for index in range(20)}}

        with pytest.raises(UnsupportedSchemaError, match="more than 20 nodes"):
            SchemaToModelFactory.make_from_json_schema(schema, class_name="Wide")

    def test_a_schema_past_the_depth_cap_is_refused(self) -> None:
        """A schema nesting deeper than the cap is refused before anything is built."""
        node: dict[str, Any] = {"type": "string"}
        for _ in range(_SchemaModelBuilder.MAX_DEPTH):
            node = {"type": "array", "items": node}
        schema = {"title": "Deep", "type": "object", "properties": {"deep": node}}

        with pytest.raises(UnsupportedSchemaError, match="nests deeper than"):
            SchemaToModelFactory.make_from_json_schema(schema, class_name="Deep")

    def test_a_schema_past_the_encoder_recursion_is_refused_as_too_deep(self) -> None:
        """A schema nesting far past the cap, deeper than the JSON encoder that keys the cache can recurse, is refused as too deep."""
        node: dict[str, Any] = {"type": "string"}
        for _ in range(100_000):
            node = {"type": "array", "items": node}
        schema = {"title": "Abyss", "type": "object", "properties": {"deep": node}}

        with pytest.raises(UnsupportedSchemaError, match="nests deeper than"):
            SchemaToModelFactory.make_from_json_schema(schema, class_name="Abyss")

    def test_a_chain_of_definitions_counts_definitions_not_nodes(self) -> None:
        """A chain of optional lists of distinct classes, many nodes deep per class, rebuilds exactly well below the definition cap."""
        schema = ModelChain.model_json_schema()
        assert len(schema["$defs"]) * 5 > _SchemaModelBuilder.MAX_DEFINITION_CHAIN

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name=ModelChain.__name__)

        assert result_class.model_json_schema() == schema
        chain = result_class.model_validate({"label": "0", "next": [{"label": "1", "next": [{"label": "2"}]}]})
        assert chain.next[0].next[0].label == "2"  # type: ignore[attr-defined]

    def test_a_recursion_error_while_building_is_refused_as_too_deep(self, mocker: MockerFixture) -> None:
        """Should the caps leave a rebuild past Python's recursion, the RecursionError is refused as a schema too deep."""
        schema, title = _unique_schema(SimpleModel)
        mocker.patch.object(_SchemaModelBuilder, "build", side_effect=RecursionError("maximum recursion depth exceeded"))

        with pytest.raises(UnsupportedSchemaError, match="references chain deeper than"):
            SchemaToModelFactory.make_from_json_schema(schema, class_name=title)

    def test_references_chaining_past_the_definition_cap_are_refused(self) -> None:
        """Definitions referencing one another in a chain longer than the cap are refused, though the schema nests shallowly."""
        chain_length = _SchemaModelBuilder.MAX_DEFINITION_CHAIN
        defs = {
            f"Link{index}": {"title": f"Link{index}", "type": "object", "properties": {"next": {"$ref": f"#/$defs/Link{index + 1}"}}}
            for index in range(chain_length)
        }
        defs[f"Link{chain_length}"] = {"title": "End", "type": "object", "properties": {}}
        schema = {"title": "Chain", "type": "object", "properties": {"first": {"$ref": "#/$defs/Link0"}}, "$defs": defs}

        with pytest.raises(UnsupportedSchemaError, match="references chain deeper than"):
            SchemaToModelFactory.make_from_json_schema(schema, class_name="Chain")
