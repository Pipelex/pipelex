from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from pipelex.system.exceptions import ConfigModelError
from pipelex.types import StrEnum

StrEnumType = TypeVar("StrEnumType", bound=StrEnum)


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @staticmethod
    def transform_dict_str_to_enum(
        input_dict: dict[str, str],
        key_enum_cls: type[StrEnumType] | None = None,
        value_enum_cls: type[StrEnumType] | None = None,
    ) -> dict[str, StrEnumType] | dict[StrEnumType, str] | dict[StrEnumType, StrEnumType]:
        """Transforms a dictionary with str values into a dictionary with enum values.

        Args:
            input_dict: Dictionary with string values to be transformed.
            key_enum_cls: The StrEnum class to convert the keys to (if needed)
            value_enum_cls: The StrEnum class to convert the values to (if needed).

        Returns:
            A dictionary where the values are converted to the given StrEnum type.

        """
        # return {key: value_enum_cls(value) for key, value in input_dict.items()}
        if key_enum_cls and value_enum_cls:
            return {key_enum_cls(key): value_enum_cls(value) for key, value in input_dict.items()}
        if key_enum_cls:
            return {key_enum_cls(key): value for key, value in input_dict.items()}
        if value_enum_cls:
            return {key: value_enum_cls(value) for key, value in input_dict.items()}
        msg = "Either key_enum_cls or value_enum_cls must be provided."
        raise ConfigModelError(msg)

    @staticmethod
    def transform_dict_of_floats_str_to_enum(
        input_dict: dict[str, float],
        key_enum_cls: type[StrEnumType],
    ) -> dict[StrEnumType, float]:
        """Transforms a dictionary with str keys and float values into a dictionary with enum keys and float values.

        Args:
            input_dict: Dictionary with string values to be transformed.
            key_enum_cls: The StrEnum class to convert the keys to

        Returns:
            A dictionary where the keys are converted to the given StrEnum type.

        """
        return {key_enum_cls(key): value for key, value in input_dict.items()}

    @staticmethod
    def transform_list_of_str_to_enum(
        input_list: list[str],
        enum_cls: type[StrEnumType],
    ) -> list[StrEnumType]:
        return [enum_cls(item) for item in input_list]
