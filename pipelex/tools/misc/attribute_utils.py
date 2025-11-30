from typing import Any, ClassVar, cast


class AttributePolisher:
    base_64_truncate_length: ClassVar[int] = 100
    url_truncate_length: ClassVar[int] = 100
    long_string_truncate_length: ClassVar[int] = 512
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

        return (name == "base_64" and len(value) > cls.base_64_truncate_length) or (
            name == "url" and isinstance(value, str) and value.startswith("data:image/") and len(value) > cls.url_truncate_length
        )

    @classmethod
    def should_truncate_any_long_string(cls, value: Any) -> bool:
        """Check if a value should be truncated based on common patterns for long strings.

        This is a more aggressive truncation that catches base64-like patterns
        regardless of field name, useful for pretty printing unknown structures.
        """
        if not isinstance(value, str):
            return False

        # Truncate data URLs (base64 images)
        if value.startswith("data:"):
            return len(value) > cls.url_truncate_length

        # Truncate any very long string that looks like base64
        # (long alphanumeric strings without spaces are likely encoded data)
        if len(value) > cls.long_string_truncate_length:
            # Check if it looks like base64: mostly alphanumeric, +, /, =
            sample = value[:200]
            base64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
            non_base64_count = sum(1 for char in sample if char not in base64_chars)
            # If less than 5% non-base64 chars, it's probably encoded data
            if non_base64_count < len(sample) * 0.05:
                return True

        return False

    @classmethod
    def get_truncated_value(cls, name: str, value: str | bytes) -> str | bytes:
        """Get the truncated value based on the field name and value type."""
        if isinstance(value, bytes):
            return cls._truncate_bytes(value, cls.base_64_truncate_length)
        if name == "base_64":
            return cls._truncate_string(value, cls.base_64_truncate_length)
        if name == "url" and value.startswith("data:image/"):
            return cls._truncate_string(value, cls.url_truncate_length)
        return value

    @classmethod
    def get_truncated_long_string(cls, value: str) -> str:
        """Truncate a long string that was detected by should_truncate_any_long_string."""
        if value.startswith("data:"):
            return cls._truncate_string(value, cls.url_truncate_length)
        return cls._truncate_string(value, cls.long_string_truncate_length)

    @classmethod
    def apply_truncation_recursive(cls, obj: Any, name: str | None = None) -> Any:
        """Recursively apply truncation logic to a data structure.

        Args:
            obj: The object to process
            name: The field name (for truncation logic)

        Returns:
            The processed object with truncation applied where appropriate

        """
        # First check if this specific object should be truncated by field name
        if name and cls.should_truncate(name=name, value=obj):
            return cls.get_truncated_value(name, obj)

        # Check for long strings that look like base64 (regardless of field name)
        if cls.should_truncate_any_long_string(obj):
            return cls.get_truncated_long_string(obj)

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
