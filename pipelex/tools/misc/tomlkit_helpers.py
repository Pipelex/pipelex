# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, cast

import tomlkit

from pipelex import pretty_print
from pipelex.tools.utils.json_utils import remove_none_values


def save_as_toml_to_path(obj: Dict[str, Any], path: str):
    json_content = remove_none_values(json_content=obj)
    cleaned_data: Dict[str, Any] = cast(Dict[str, Any], json_content)

    pretty_print(cleaned_data, title="Saving toml to path")

    with open(path, "w") as fp:
        tomlkit.dump(  # type: ignore
            data=cleaned_data,
            fp=fp,
            sort_keys=True,
        )
