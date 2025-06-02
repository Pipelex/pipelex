from typing import Any, Dict, Optional, Type, TypeVar, Union

from pydantic import BaseModel, ConfigDict, ValidationError

from pipelex.tools.exceptions import ConfigModelError, ConfigValidationError
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import StrEnum

CONFIG_BASE_OVERRIDES_BEFORE_ENV = ["local"]
CONFIG_BASE_OVERRIDES_AFTER_ENV = ["super"]


class SecretMethod(StrEnum):
    NONE = "none"
    ENV_VAR = "env_var"
    SECRET_PROVIDER = "secret_provider"


StrEnumType = TypeVar("StrEnumType", bound=StrEnum)


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @staticmethod
    def transform_dict_str_to_enum(
        input_dict: Dict[str, str],
        key_enum_cls: Optional[Type[StrEnumType]] = None,
        value_enum_cls: Optional[Type[StrEnumType]] = None,
    ) -> Union[Dict[str, StrEnumType], Dict[StrEnumType, str], Dict[StrEnumType, StrEnumType]]:
        """
        Transforms a dictionary with str values into a dictionary with enum values.

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
        elif key_enum_cls:
            return {key_enum_cls(key): value for key, value in input_dict.items()}
        elif value_enum_cls:
            return {key: value_enum_cls(value) for key, value in input_dict.items()}
        else:
            raise ConfigModelError("Either key_enum_cls or value_enum_cls must be provided.")


class ConfigRoot(ConfigModel):
    """
    Main configuration class for the project.

    Attributes:
        project_name (str): Name of the current project.
    """

    project_name: Optional[str] = None

    def __init__(self, **kwargs: Any):
        """
        Initialize the Config instance.

        Args:
            **kwargs: Keyword arguments for configuration.

        Raises:
            ConfigValidationError: If the provided data is invalid.
        """

        try:
            super().__init__(**kwargs)
        except ValidationError as exc:
            validation_error_msg = format_pydantic_validation_error(exc)
            error_msg = f"Could not create config of type {type(self)} with provided data: {validation_error_msg}"
            raise ConfigValidationError(message=error_msg) from exc
