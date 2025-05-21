# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Iterable, Optional, Sequence, Tuple

import rich
from pydantic import BaseModel
from rich.repr import Result as RichReprResult
from typing_extensions import override

TRUNCATE_LENGTH = 50
TRUNCATE_SUFFIX = "…"


class CustomBaseModel(BaseModel):
    @override
    def __rich_repr__(self) -> RichReprResult:  # type: ignore
        for item in super().__rich_repr__():  # type: ignore
            if isinstance(item, tuple) and len(item) >= 2:
                name = item[0]
                value = item[1]
                if name == "base_64" and isinstance(value, str) and len(value) > TRUNCATE_LENGTH:
                    truncated_value = value[:TRUNCATE_LENGTH] + TRUNCATE_SUFFIX
                    if len(item) == 3:
                        yield name, truncated_value, item[2]
                    else:
                        yield name, truncated_value
                else:
                    yield item
            else:
                yield item

    @override
    def __repr_args__(self) -> Sequence[tuple[Optional[str], Any]]:
        processed_args: list[tuple[Optional[str], Any]] = []
        for name, value in super().__repr_args__():
            if name == "base_64" and isinstance(value, str) and len(value) > TRUNCATE_LENGTH:
                processed_args.append((name, value[:TRUNCATE_LENGTH] + TRUNCATE_SUFFIX))
            else:
                processed_args.append((name, value))
        return processed_args
