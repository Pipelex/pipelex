# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import os
from typing import Optional

from dotenv import load_dotenv

from pipelex.tools.exceptions import FatalError

load_dotenv(dotenv_path=".env", override=True)


class EnvVarNotFoundError(FatalError):
    pass


def get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvVarNotFoundError(f"Missing '{key} 'in environment.")
    return value


def get_optional_env(key: str) -> Optional[str]:
    value = os.getenv(key)
    return value


def set_env(key: str, value: str) -> None:
    os.environ[key] = value
    return None


def get_rooted_path(root: str, path: Optional[str] = None) -> str:
    if path is None:
        path = ""
    if path.startswith(root):
        return path
    elif os.path.isabs(path):
        return path
    else:
        joined = os.path.join(root, path)
        # remove edning "/" if any
        if joined.endswith("/"):
            joined = joined[:-1]
        return joined


def get_env_rooted_path(root_env: str, path: Optional[str] = None) -> str:
    root = os.getenv(root_env)
    if root is None:
        root = ""
    return get_rooted_path(root, path)
