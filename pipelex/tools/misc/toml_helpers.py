# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, Optional

import toml

from pipelex.tools.utils.path_utils import path_exists


def load_toml_from_path(path: str) -> Dict[str, Any]:
    with open(path) as file:
        dict_from_toml = toml.load(file)
        return dict_from_toml


def failable_load_toml_from_path(path: str) -> Optional[Dict[str, Any]]:
    if not path_exists(path):
        return None
    return load_toml_from_path(path)
