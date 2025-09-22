import os
from typing import List, Optional

from dotenv import load_dotenv

from pipelex.tools.exceptions import ToolException
from pipelex.tools.misc.placeholder import value_is_placeholder

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


def is_env_var_set(key: str) -> bool:
    return os.getenv(key) is not None


def all_env_vars_are_set(keys: List[str]) -> bool:
    for each_key in keys:
        if not is_env_var_set(each_key):
            return False
    return True


def any_env_var_is_placeholder(keys: List[str]) -> bool:
    for each_key in keys:
        env_value = os.getenv(each_key)
        if value_is_placeholder(env_value):
            return True
    return False


def set_env(key: str, value: str) -> None:
    os.environ[key] = value
    return None
