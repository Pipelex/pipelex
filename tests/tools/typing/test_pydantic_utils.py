from enum import StrEnum
from typing import Any, Dict, cast

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipelex.tools.typing.pydantic_utils import (
    CustomBaseModel,
    ExtraFieldAttribute,
    clean_model_to_dict,
    convert_strenum_to_str,
    format_pydantic_validation_error,
    serialize_model,
)


class ChildModel(BaseModel):
    child_name: str
    child_secret: str = Field(
        ...,
        json_schema_extra={ExtraFieldAttribute.IS_HIDDEN: True},  # This field should be hidden
    )


class ParentModel(BaseModel):
    parent_name: str
    child: ChildModel


def test_serialize_model_with_hidden_fields():
    # Create nested models
    child = ChildModel(child_name="foo", child_secret="secret_foo")
    parent = ParentModel(parent_name="bar", child=child)

    # Test default model_dump() shows everything
    model_dump_result: Dict[str, Any] = parent.model_dump()
    child_dict = cast(Dict[str, Any], model_dump_result["child"])
    assert "child_secret" in child_dict
    assert child_dict["child_secret"] == "secret_foo"

    # Test our custom serializer omits hidden fields (child_secret)
    serialized_result = cast(Dict[str, Any], serialize_model(parent))
    child_serialized = cast(Dict[str, Any], serialized_result["child"])
    assert "child_secret" not in child_serialized
    assert serialized_result == {"parent_name": "bar", "child": {"child_name": "foo"}}


class SimpleEnum(StrEnum):
    FIRST = "first"
    SECOND = "second"

    def display_name(self) -> str:  # pragma: no cover - simple helper
        return self.value.upper()


class ModelWithEnum(BaseModel):
    name: str
    enum_val: SimpleEnum
    secret: str = Field(
        "hidden",
        json_schema_extra={ExtraFieldAttribute.IS_HIDDEN: True},
    )


def test_clean_model_to_dict_stringifies_enums_and_hides_fields() -> None:
    model = ModelWithEnum(name="foo", enum_val=SimpleEnum.FIRST, secret="hidden")
    result = clean_model_to_dict(model)
    assert result == {"name": "foo", "enum_val": "FIRST"}


def test_convert_strenum_to_str_recursive() -> None:
    data = {
        "enum": SimpleEnum.SECOND,
        "nested": [SimpleEnum.FIRST, {"e": SimpleEnum.SECOND}],
    }
    converted = convert_strenum_to_str(data)
    assert converted == {
        "enum": "SECOND",
        "nested": ["FIRST", {"e": "SECOND"}],
    }


def test_format_pydantic_validation_error() -> None:
    class Validated(BaseModel):
        model_config = ConfigDict(extra="forbid")
        a: int
        b: str

    with pytest.raises(ValidationError) as exc:
        Validated.model_validate({"a": "not_int", "c": 1})

    formatted = format_pydantic_validation_error(exc.value)
    assert "Missing required fields: ['b']" in formatted
    assert "Extra forbidden fields: ['c: 1']" in formatted


def test_custom_base_model_truncates_repr() -> None:
    class TestModel(CustomBaseModel):
        base_64: str
        url: str
        other: str

    TestModel.truncate_length = 10
    model = TestModel(
        base_64="b" * 20,
        url="data:image/png;base64," + "x" * 20,
        other="val",
    )
    repr_str = repr(model)
    assert "bbbbbbbbbb…" in repr_str
    assert "data:image…" in repr_str
