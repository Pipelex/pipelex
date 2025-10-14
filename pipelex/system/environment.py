import os

from dotenv import load_dotenv

from pipelex.system.exceptions import ToolException
from pipelex.tools.misc.placeholder import value_is_placeholder

load_dotenv(dotenv_path=".env", override=True)


class EnvVarNotFoundError(ToolException):
    pass


def get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        msg = f"Environment variable '{key}' is required but not set"
        raise EnvVarNotFoundError(msg)
    return value


def get_optional_env(key: str) -> str | None:
    return os.getenv(key)


def is_env_var_set(key: str) -> bool:
    return os.getenv(key) is not None


def all_env_vars_are_set(keys: list[str]) -> bool:
    return all(is_env_var_set(each_key) for each_key in keys)


def any_env_var_is_placeholder(keys: list[str]) -> bool:
    for each_key in keys:
        env_value = os.getenv(each_key)
        if value_is_placeholder(env_value):
            return True
    return False


def set_env(key: str, value: str) -> None:
    os.environ[key] = value
