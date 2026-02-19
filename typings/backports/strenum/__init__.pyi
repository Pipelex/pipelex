import enum

class StrEnum(str, enum.Enum):  # noqa: UP042
    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str: ...  # type: ignore[override]
