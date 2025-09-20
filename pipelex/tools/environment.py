import os
from typing import Iterable, Optional

from dotenv import load_dotenv

from pipelex.tools.exceptions import ToolException

ENV_DUMMY_PLACEHOLDER_VALUE = "env-dummy-placeholder"

load_dotenv(dotenv_path=".env", override=True)


class EnvVarNotFoundError(ToolException):
    pass


def get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvVarNotFoundError(f"Environment variable '{key}' is required but not set")
    return value


def get_optional_env(key: str) -> Optional[str]:
    value = os.getenv(key)
    return value


def is_env_set(keys: Iterable[str]) -> bool:
    for each_key in keys:
        if os.getenv(each_key) is None:
            return False
    return True


def any_is_placeholder_env(keys: Iterable[str]) -> bool:
    for each_key in keys:
        if os.getenv(each_key) == ENV_DUMMY_PLACEHOLDER_VALUE:
            return True
    return False


def set_env(key: str, value: str) -> None:
    os.environ[key] = value
    return None
