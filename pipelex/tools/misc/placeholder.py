PLACEHOLDER_PREFIX = "placeholder"


def make_placeholder_value(key: str) -> str:
    """Create a placeholder value for a given key.

    Args:
        key: The key/variable name to create a placeholder for

    Returns:
        A placeholder value in the format "placeholder-for-{key}"

    """
    return f"{PLACEHOLDER_PREFIX}-for-{key}"


def value_is_placeholder(value: str | None) -> bool:
    """Check if a value is a placeholder based on the prefix.

    Args:
        value: The value to check

    Returns:
        True if the value starts with the placeholder prefix, False otherwise

    """
    return value is not None and value.startswith(PLACEHOLDER_PREFIX)
