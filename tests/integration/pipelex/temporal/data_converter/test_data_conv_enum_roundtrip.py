from typing import cast

import pytest
from pydantic import BaseModel

from pipelex import pretty_print
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.temporal.temporal_data_converter import BaseModelPayloadConverter
from pipelex.types import StrEnum


class PetSpecies(StrEnum):
    DOG = "dog"
    CAT = "cat"


class Pet(BaseModel):
    name: str
    species: PetSpecies


@pytest.mark.temporal
class TestEnumRoundTrip:
    def test_dynamic_class_with_enum_field_round_trips(
        self,
        payload_converter: BaseModelPayloadConverter,
    ):
        """A class with an enum-shaped field generated via SchemaToModelFactory must
        survive a full payload round-trip. Exercises the receiver-side exec path that
        rebuilds the dynamic class from `__kajson_class_source__` — without it the
        deserializer cannot resolve the dynamic class and the round-trip fails.
        """
        schema = Pet.model_json_schema()
        dynamic_pet_cls = SchemaToModelFactory.make_from_json_schema(schema, "Pet")
        instance = dynamic_pet_cls(name="Rex", species=PetSpecies.DOG)
        pretty_print(instance, title="instance")

        payload = payload_converter.to_payload(instance)
        pretty_print(payload, title="payload")
        assert payload is not None
        assert payload.metadata.get("kajson_class_source")

        restored = cast("BaseModel", payload_converter.from_payload(payload, type_hint=BaseModel))
        pretty_print(restored, title="restored")

        restored_class: type[BaseModel] = type(restored)
        assert restored_class.__name__ == "Pet"
        # datamodel-code-generator now emits enum-shaped `$defs` as
        # `RootModel[Literal[...]]` (since `enum_field_as_literal=LiteralType.All` is
        # set in `_generate_source_from_schema`), so `restored.species` is a
        # `RootModel` wrapping the value, not a Python `Enum` instance. Assert on the
        # serialized data — that is what actually crosses the Temporal payload boundary.
        assert restored.model_dump() == {"name": "Rex", "species": "dog"}
        assert getattr(restored_class, "__kajson_class_source__", None)
