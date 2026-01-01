from typing import Any, ClassVar, cast


class AttributePolisher:
    bytes_truncate_length: ClassVar[int] = 100
    url_truncate_length: ClassVar[int] = 100
    base64_truncate_length: ClassVar[int] = 128
    text_truncate_length: ClassVar[int] = 2048
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
            return value[:max_length]
        return value

    @classmethod
    def should_truncate(cls, value: Any) -> bool:
        if isinstance(value, str):
            if value.startswith("http"):
                return len(value) > cls.url_truncate_length
            elif value.startswith("data:") or cls._looks_like_base64(value):
                return len(value) > cls.base64_truncate_length
            else:
                return len(value) > cls.text_truncate_length
        if isinstance(value, bytes):
            return len(value) > cls.bytes_truncate_length
        return False

    @classmethod
    def get_truncated_value(cls, value: Any) -> Any:
        """Get the truncated value based on the field name and value type."""
        if isinstance(value, bytes):
            return cls._truncate_bytes(value, cls.bytes_truncate_length)
        elif isinstance(value, str):
            if value.startswith("http"):
                return cls._truncate_string(value, cls.url_truncate_length)
            elif value.startswith("data:") or cls._looks_like_base64(value):
                return cls._truncate_string(value, cls.base64_truncate_length)
            else:
                return cls._truncate_string(value, cls.text_truncate_length)
        return value

    @classmethod
    def _looks_like_base64(cls, value: str) -> bool:
        """Check if a string looks like base64 encoded data."""
        if value.startswith("data:"):
            return True
        # Check if it looks like base64: mostly alphanumeric, +, /, =
        sample = value[:200]
        base64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        non_base64_count = sum(1 for char in sample if char not in base64_chars)
        # If less than 5% non-base64 chars, it's probably encoded data
        return non_base64_count < len(sample) * 0.05

    @classmethod
    def apply_truncation_recursive(cls, obj: Any, name: str | None = None) -> Any:
        """Recursively apply truncation logic to a data structure.

        Args:
            obj: The object to process
            name: The field name (for truncation logic)

        Returns:
            The processed object with truncation applied where appropriate

        """
        # First check if this specific object should be truncated
        if cls.should_truncate(value=obj):
            return cls.get_truncated_value(value=obj)

        # If it's a dictionary, recurse into its values
        if isinstance(obj, dict):
            obj_dict = cast("dict[str, Any]", obj)
            truncated_dict: dict[str, Any] = {}
            for key, value in obj_dict.items():
                truncated_dict[key] = cls.apply_truncation_recursive(value, name=key)
            return truncated_dict

        # If it's a list, recurse into its items
        if isinstance(obj, list):
            obj_list = cast("list[Any]", obj)
            return [cls.apply_truncation_recursive(item, name=name) for item in obj_list]

        # If it's a tuple, recurse into its items and return as tuple
        if isinstance(obj, tuple):
            return tuple(cls.apply_truncation_recursive(item, name=name) for item in obj)  # pyright: ignore[reportUnknownVariableType]

        # For all other types, return as-is
        return obj
