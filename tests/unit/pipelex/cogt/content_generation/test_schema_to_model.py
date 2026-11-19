"""Unit tests for SchemaToModelFactory: rebuilding BaseModel classes from JSON schemas with create_model."""

import threading
import uuid
from enum import StrEnum
from typing import Any, Literal, get_args, get_origin

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, Field, ValidationError
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.exceptions import UnsupportedSchemaError
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory, _SchemaModelBuilder  # pyright: ignore[reportPrivateUsage]
from pipelex.system.registries.class_registry_access import get_class_registry
from tests.unit.pipelex.cogt.content_generation.test_data import SchemaRebuildTestData


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

    def test_a_field_with_a_default_factory_starts_empty(self) -> None:
        """A container the schema shows as optional with no default starts empty on the rebuilt class, as its factory made it."""
        schema = ModelWithConstraints.model_json_schema()
        schema["properties"]["tags"] = {"items": {"type": "string"}, "title": "Tags", "type": "array"}
        schema["required"] = ["score", "code"]
        schema["title"] = f"FactoryDefaults_{uuid.uuid4().hex}"

        result_class = SchemaToModelFactory.make_from_json_schema(schema, class_name="FactoryDefaults")

        assert result_class.model_validate({"score": 1, "code": "AB"}).model_dump() == {"score": 1.0, "code": "AB", "tags": [], "ratio": None}
        assert result_class.model_json_schema() == schema

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

    def test_references_chaining_past_the_depth_cap_are_refused(self) -> None:
        """Definitions referencing one another in a chain longer than the cap are refused, though the schema nests shallowly."""
        chain_length = _SchemaModelBuilder.MAX_DEPTH
        defs = {
            f"Link{index}": {"title": f"Link{index}", "type": "object", "properties": {"next": {"$ref": f"#/$defs/Link{index + 1}"}}}
            for index in range(chain_length)
        }
        defs[f"Link{chain_length}"] = {"title": "End", "type": "object", "properties": {}}
        schema = {"title": "Chain", "type": "object", "properties": {"first": {"$ref": "#/$defs/Link0"}}, "$defs": defs}

        with pytest.raises(UnsupportedSchemaError, match="references chain deeper than"):
            SchemaToModelFactory.make_from_json_schema(schema, class_name="Chain")
