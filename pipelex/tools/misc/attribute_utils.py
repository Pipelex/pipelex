from typing import Any, ClassVar, Union


class AttributePolisher:
    base_64_truncate_length: ClassVar[int] = 64
    url_truncate_length: ClassVar[int] = 128
    truncate_suffix: ClassVar[str] = "…"

    @classmethod
    def _truncate_string(cls, value: str, max_length: int) -> str:
        """Truncate a string to the specified maximum length and append the truncate suffix."""
        if len(value) > max_length:
            return value[:max_length] + cls.truncate_suffix
        return value

    @classmethod
    def _truncate_bytes(cls, value: bytes, max_length: int) -> bytes:
        """Truncate a bytes to the specified maximum length and append the truncate suffix."""
        if len(value) > max_length:
            return value[:max_length] + cls.truncate_suffix.encode("utf-8")
        return value

    @classmethod
    def should_truncate(cls, name: str, value: Any) -> bool:
        if not isinstance(value, (str, bytes)):
            return False

        if name == "base_64" and len(value) > cls.base_64_truncate_length:
            return True
        elif name == "url" and isinstance(value, str) and value.startswith("data:image/") and len(value) > cls.url_truncate_length:
            return True
        return False

    @classmethod
    def get_truncated_value(cls, name: str, value: Union[str, bytes]) -> Union[str, bytes]:
        """Get the truncated value based on the field name and value type."""
        if isinstance(value, bytes):
            return cls._truncate_bytes(value, cls.base_64_truncate_length)
        elif name == "base_64":
            return cls._truncate_string(value, cls.base_64_truncate_length)
        elif name == "url" and value.startswith("data:image/"):
            return cls._truncate_string(value, cls.url_truncate_length)
        return value
