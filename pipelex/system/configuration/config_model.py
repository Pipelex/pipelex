from enum import StrEnum
from typing import Annotated, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, Strict

StrEnumType = TypeVar("StrEnumType", bound=StrEnum)

# A `StrEnum` read leniently, so a TOML string converts to its member, inside a container that stays strict.
# `Field(strict=False)` on a field does not reach a container's items: `list[MyEnum] = Field(strict=False)`
# still refuses `["a_member"]`. Write `list[LaxEnum[MyEnum]]` or `dict[LaxEnum[MyEnum], ...]` instead, and
# never convert the items by hand in a `mode="before"` validator, which would see the raw value of any type.
LaxEnum: TypeAlias = Annotated[StrEnumType, Strict(False)]


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
