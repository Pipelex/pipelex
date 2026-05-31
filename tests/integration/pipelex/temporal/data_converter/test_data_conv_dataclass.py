"""Direct converter round-trip tests for pydantic dataclasses.

Phase 0 widened ``BaseModelPayloadConverter`` so a pydantic dataclass (and ``Optional`` /
``list`` of them) routes through kajson with type preservation, instead of falling through
to Temporal's stock JSON. These call ``to_payload`` / ``from_payload`` directly and assert
both value and concrete type survive. A regression guard locks the untouched ``BaseModel``
path to byte-identical output.
"""

from datetime import timedelta
from typing import Any, cast

import pytest
from kajson import kajson
from pydantic import BaseModel
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic.dataclasses import is_pydantic_dataclass

from pipelex.temporal.temporal_data_converter import BaseModelPayloadConverter


class ConvInner(BaseModel):
    label: str
    count: int


@pydantic_dataclass
class ConvDataclass:
    name: str
    delay: timedelta
    inner: ConvInner
    note: str | None = None


class ConvPlainModel(BaseModel):
    field_a: str
    field_b: int


@pytest.mark.temporal
class TestDataConverterForPydanticDataclass:
    def test_scalar_dataclass_roundtrip(self, payload_converter: BaseModelPayloadConverter) -> None:
        original = ConvDataclass(name="x", delay=timedelta(seconds=30), inner=ConvInner(label="L", count=2))
        payload = payload_converter.to_payload(original)
        assert payload
        restored = cast("ConvDataclass", payload_converter.from_payload(payload, type_hint=ConvDataclass))
        assert is_pydantic_dataclass(type(restored))
        assert isinstance(restored.inner, ConvInner)
        assert restored == original

    def test_optional_dataclass_roundtrip(self, payload_converter: BaseModelPayloadConverter) -> None:
        original = ConvDataclass(name="opt", delay=timedelta(seconds=5), inner=ConvInner(label="O", count=1), note="set")
        payload = payload_converter.to_payload(original)
        assert payload
        optional_hint: Any = ConvDataclass | None
        restored = cast("ConvDataclass", payload_converter.from_payload(payload, type_hint=optional_hint))
        assert is_pydantic_dataclass(type(restored))
        assert restored == original

    def test_list_of_dataclass_roundtrip(self, payload_converter: BaseModelPayloadConverter) -> None:
        original = [
            ConvDataclass(name="a", delay=timedelta(seconds=1), inner=ConvInner(label="A", count=1)),
            ConvDataclass(name="b", delay=timedelta(seconds=2), inner=ConvInner(label="B", count=2)),
        ]
        payload = payload_converter.to_payload(original)
        assert payload
        list_hint: Any = list[ConvDataclass]
        restored = cast("list[ConvDataclass]", payload_converter.from_payload(payload, type_hint=list_hint))
        assert all(is_pydantic_dataclass(type(item)) for item in restored)
        assert all(isinstance(item.inner, ConvInner) for item in restored)
        assert restored == original

    def test_base_model_payload_is_byte_identical(self, payload_converter: BaseModelPayloadConverter) -> None:
        # Regression guard: the dataclass widening must leave the BaseModel path byte-identical.
        # A plain BaseModel (no __kajson_class_source__) yields exactly kajson.dumps bytes plus the
        # encoding metadata key — nothing the dataclass branch could perturb.
        model = ConvPlainModel(field_a="hello", field_b=7)
        payload = payload_converter.to_payload(model)
        assert payload
        assert set(payload.metadata.keys()) == {"encoding"}
        assert payload.metadata["encoding"] == payload_converter.encoding.encode()
        assert payload.data == kajson.dumps(model).encode()
        restored = cast("ConvPlainModel", payload_converter.from_payload(payload, type_hint=ConvPlainModel))
        assert restored == model
