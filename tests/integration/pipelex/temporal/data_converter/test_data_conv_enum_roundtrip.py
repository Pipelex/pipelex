from enum import Enum
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
        """A class with an Enum field generated via SchemaToModelFactory must survive a
        full payload round-trip. Exercises the receiver-side exec path that registers
        Enum subclasses in the per-call scoped ClassRegistry — without it the
        deserializer cannot resolve the dynamic enum class and the round-trip fails.
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
        assert restored.name == "Rex"  # type: ignore[attr-defined]
        # datamodel-code-generator emits `class PetSpecies(Enum)` (not StrEnum), so the
        # dynamic enum is a distinct class from the static PetSpecies above. Assert on
        # class name + value instead of identity equality.
        species_value: Enum = restored.species  # type: ignore[attr-defined]
        assert isinstance(species_value, Enum)
        assert type(species_value).__name__ == "PetSpecies"
        assert species_value.value == "dog"
        assert getattr(restored_class, "__kajson_class_source__", None)
