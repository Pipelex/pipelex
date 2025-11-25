from pipelex.tools.misc.string_utils import is_snake_case


def is_valid_input_name(input_name: str) -> bool:
    """Check if an input name is valid.

    An input name is valid if:
    - It's not empty
    - It doesn't start or end with a dot
    - All parts separated by dots are in snake_case
    - There are no consecutive dots

    Args:
        input_name: The input name to validate

    Returns:
        bool: True if the input name is valid, False otherwise

    Examples:
        >>> is_valid_input_name("my_input")
        True
        >>> is_valid_input_name("my_input.field_name")
        True
        >>> is_valid_input_name("my_input.field_name.nested_field")
        True
        >>> is_valid_input_name("myInput")
        False
        >>> is_valid_input_name("my_input.fieldName")
        False
        >>> is_valid_input_name("")
        False
        >>> is_valid_input_name(".")
        False
        >>> is_valid_input_name(".my_input")
        False
        >>> is_valid_input_name("my_input.")
        False
        >>> is_valid_input_name("my_input..field")
        False

    """
    if not input_name:
        return False

    # Check for leading/trailing dots or consecutive dots
    if input_name.startswith(".") or input_name.endswith(".") or ".." in input_name:
        return False

    # Split by dots and validate each part is snake_case
    parts = input_name.split(".")
    return all(is_snake_case(part) for part in parts)


def validate_input_name(input_name: str) -> None:
    """Validate an input name and raise an error if invalid.

    Args:
        input_name: The input name to validate

    Raises:
        ValueError: If the input name is invalid

    """
    if not is_valid_input_name(input_name):
        msg = (
            f"Invalid input name syntax '{input_name}'. "
            "Input names must be in snake_case. "
            "Nested field access is allowed using dots (e.g., 'my_input.field_name'), "
            "where each part must also be in snake_case."
        )
        raise ValueError(msg)
