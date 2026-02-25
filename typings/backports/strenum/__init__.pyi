import enum

from typing_extensions import Self

class StrEnum(str, enum.Enum):  # noqa: UP042
    def __new__(cls, value: str) -> Self: ...
    _value_: str
    @property
    def value(self) -> str: ...  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str: ...  # type: ignore[override]
