"""Regression guard: model_dump(serialize_as_any=True) roundtrip for schema-reconstructed models.

content_generator.py uses `object_class.model_validate(raw_obj.model_dump(serialize_as_any=True))`
where raw_obj is a dynamically-reconstructed BaseModel from SchemaToModelFactory. This test verifies
the roundtrip preserves all data, including nested models.
"""

from pydantic import BaseModel, Field

from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory


class InnerDetail(BaseModel):
    label: str = Field(description="A label")
    value: int = Field(description="A numeric value")


class OuterModel(BaseModel):
    title: str = Field(description="The title")
    detail: InnerDetail = Field(description="Nested detail object")


class TestModelDumpSubclass:
    def test_reconstructed_flat_model_roundtrip(self) -> None:
        """Flat reconstructed model roundtrips through model_dump(serialize_as_any=True) → model_validate."""
        schema = InnerDetail.model_json_schema()
        reconstructed_class = SchemaToModelFactory.make_from_json_schema(schema, "InnerDetail")

        raw_obj: BaseModel = reconstructed_class(label="score", value=42)

        dumped = raw_obj.model_dump(serialize_as_any=True)
        restored = InnerDetail.model_validate(dumped)
        assert restored.label == "score"
        assert restored.value == 42

    def test_reconstructed_nested_model_roundtrip(self) -> None:
        """Nested reconstructed model roundtrips through model_dump(serialize_as_any=True) → model_validate."""
        schema = OuterModel.model_json_schema()
        reconstructed_class = SchemaToModelFactory.make_from_json_schema(schema, "OuterModel")

        raw_obj: BaseModel = reconstructed_class(
            title="Test",
            detail={"label": "score", "value": 42},
        )

        dumped = raw_obj.model_dump(serialize_as_any=True)
        restored = OuterModel.model_validate(dumped)
        assert restored.title == "Test"
        assert restored.detail.label == "score"
        assert restored.detail.value == 42
