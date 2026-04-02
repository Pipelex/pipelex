"""Unit tests for schema_to_model: reconstructing BaseModel classes from JSON schemas."""

from pydantic import BaseModel, Field

from pipelex.cogt.content_generation.schema_to_model import model_class_from_json_schema


class SimpleModel(BaseModel):
    name: str = Field(description="The name")
    age: int = Field(description="The age")


class Address(BaseModel):
    street: str
    city: str


class PersonWithAddress(BaseModel):
    name: str
    address: Address


class TestSchemaToModel:
    def test_simple_model_reconstruction(self) -> None:
        """A simple model can be reconstructed from its JSON schema."""
        schema = SimpleModel.model_json_schema()
        result_class = model_class_from_json_schema(schema, "SimpleModel")

        assert result_class.__name__ == "SimpleModel"
        assert "name" in result_class.model_fields
        assert "age" in result_class.model_fields

    def test_reconstructed_model_can_validate(self) -> None:
        """The reconstructed model can validate data."""
        schema = SimpleModel.model_json_schema()
        result_class = model_class_from_json_schema(schema, "SimpleModel")

        instance = result_class(name="Alice", age=30)
        assert instance.name == "Alice"  # type: ignore[attr-defined]
        assert instance.age == 30  # type: ignore[attr-defined]

    def test_nested_model_reconstruction(self) -> None:
        """A model with nested BaseModel fields (producing $defs) can be reconstructed."""
        schema = PersonWithAddress.model_json_schema()
        result_class = model_class_from_json_schema(schema, "PersonWithAddress")

        instance = result_class(
            name="Bob",
            address={"street": "123 Main", "city": "NYC"},
        )
        assert instance.name == "Bob"  # type: ignore[attr-defined]
        assert instance.address.city == "NYC"  # type: ignore[attr-defined]

    def test_kajson_class_source_attached(self) -> None:
        """The reconstructed class has __kajson_class_source__ with the generated Python source."""
        schema = SimpleModel.model_json_schema()
        result_class = model_class_from_json_schema(schema, "SimpleModel")

        source = getattr(result_class, "__kajson_class_source__", None)
        assert source is not None
        assert "class SimpleModel" in source
        assert "BaseModel" in source

    def test_caching_returns_same_class(self) -> None:
        """Calling with the same schema returns the same class object (cached)."""
        schema = SimpleModel.model_json_schema()
        class_1 = model_class_from_json_schema(schema, "SimpleModel")
        class_2 = model_class_from_json_schema(schema, "SimpleModel")

        assert class_1 is class_2

    def test_different_schemas_different_classes(self) -> None:
        """Different schemas produce different classes even if class names differ."""
        schema_simple = SimpleModel.model_json_schema()
        schema_nested = PersonWithAddress.model_json_schema()

        class_simple = model_class_from_json_schema(schema_simple, "SimpleModel")
        class_nested = model_class_from_json_schema(schema_nested, "PersonWithAddress")

        assert class_simple is not class_nested

    def test_json_roundtrip_with_reconstructed_class(self) -> None:
        """An instance of the reconstructed class survives JSON round-trip."""
        schema = SimpleModel.model_json_schema()
        result_class = model_class_from_json_schema(schema, "SimpleModel")

        instance = result_class(name="Charlie", age=25)
        json_str = instance.model_dump_json()
        restored = result_class.model_validate_json(json_str)
        assert restored.name == "Charlie"  # type: ignore[attr-defined]
        assert restored.age == 25  # type: ignore[attr-defined]

    def test_normalized_class_name_lookup(self) -> None:
        """A class_name with underscores/double-underscores resolves via PascalCase normalization."""
        schema = SimpleModel.model_json_schema()
        # Override the title to simulate a dynamic concept code like "my_namespace__Greeting"
        schema["title"] = "my_namespace__Greeting"
        result_class = model_class_from_json_schema(schema, "my_namespace__Greeting")

        assert "name" in result_class.model_fields
        assert "age" in result_class.model_fields
        instance = result_class(name="Ada", age=40)
        assert instance.name == "Ada"  # type: ignore[attr-defined]
