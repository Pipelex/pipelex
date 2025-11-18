from pydantic import BaseModel, Field

from pipelex.tools.typing.pydantic_utils import (
    ExtraFieldAttribute,
    clean_model_to_dict,
    convert_strenum_to_str,
)
from pipelex.types import StrEnum


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


class TestEnumUtilities:
    """Tests for enum utility functions."""

    def test_clean_model_to_dict_stringifies_enums_and_hides_fields(self) -> None:
        """Test that clean_model_to_dict converts enums to strings and hides marked fields."""
        model = ModelWithEnum(name="foo", enum_val=SimpleEnum.FIRST, secret="hidden")
        result = clean_model_to_dict(model)
        assert result == {"name": "foo", "enum_val": "FIRST"}

    def test_convert_strenum_to_str_recursive(self) -> None:
        """Test that convert_strenum_to_str recursively converts enums in nested structures."""
        data = {
            "enum": SimpleEnum.SECOND,
            "nested": [SimpleEnum.FIRST, {"e": SimpleEnum.SECOND}],
        }
        converted = convert_strenum_to_str(data)
        assert converted == {
            "enum": "SECOND",
            "nested": ["FIRST", {"e": "SECOND"}],
        }
