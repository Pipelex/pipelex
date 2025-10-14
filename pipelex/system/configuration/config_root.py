from typing import Any

from pydantic import ValidationError

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.exceptions import ConfigValidationError
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import StrEnum

CONFIG_BASE_OVERRIDES_BEFORE_ENV = ["local"]
CONFIG_BASE_OVERRIDES_AFTER_ENV = ["super"]


class SecretMethod(StrEnum):
    NONE = "none"
    ENV_VAR = "env_var"
    SECRET_PROVIDER = "secret_provider"


class ConfigRoot(ConfigModel):
    """Main configuration class for the project.

    Attributes:
        project_name (str): Name of the current project.

    """

    project_name: str | None = None

    def __init__(self, **kwargs: Any):
        """Initialize the Config instance.

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
