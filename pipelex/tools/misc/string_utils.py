import re
from typing import Any, List, Optional


def has_text(text: str) -> bool:
    """
    Checks if a string contains any alphanumeric characters.

    This function uses a regex pattern to check for the presence of any alphanumeric
    character, including non-ASCII characters (e.g., é, ñ, etc.).

    Args:
        text (str): The string to check for alphanumeric content.

    Returns:
        bool: True if the string contains at least one alphanumeric character, False otherwise.
    """
    return bool(re.search(r"\w", text))


def is_none_or_has_text(text: Optional[str]) -> bool:
    """
    Checks if a string is None or contains alphanumeric characters.

    This function combines a None check with the has_text function to validate that
    a string is either None or contains meaningful content.

    Args:
        text (Optional[str]): The string to check, which can be None.

    Returns:
        bool: True if the string is None or contains at least one alphanumeric character,
              False if it's an empty string or contains only non-alphanumeric characters.
    """
    return text is None or has_text(text)


def can_inject_text(value: Optional[Any]) -> bool:
    """
    Checks if a value can be safely converted to a string containing alphanumeric characters.

    This function attempts to convert any value to a string and checks if it contains
    alphanumeric characters. It handles None values and exceptions gracefully, making it
    safe for type-uncertain inputs.

    Args:
        value (Optional[Any]): Any value that might be convertible to a string, including None.

    Returns:
        bool: True if the value can be converted to a string containing alphanumeric characters,
              False if the value is None, empty, or cannot be safely converted to a string.
    """
    if not value:
        return False
    try:
        return has_text(f"{value}")
    except Exception:
        return False


def is_not_none_and_has_text(text: Optional[str]) -> bool:
    """
    Checks if a string is not None and contains alphanumeric characters.

    This function combines a None check with the has_text function to validate that
    a string exists and contains meaningful content. It's the opposite of is_none_or_has_text.

    Args:
        text (Optional[str]): The string to check, which can be None.

    Returns:
        bool: True if the string is not None and contains at least one alphanumeric character,
              False if it's None, empty, or contains only non-alphanumeric characters.
    """
    return text is not None and has_text(text)


def camel_to_snake_case(name: str) -> str:
    """
    Converts a camelCase string to snake_case format.

    This function identifies word boundaries in camelCase by looking for transitions
    between lowercase and uppercase letters, then joins the words with underscores.

    Args:
        name (str): The camelCase string to convert (e.g., "myVariableName").

    Returns:
        str: The snake_case version of the string (e.g., "my_variable_name").

    Example:
        >>> camel_to_snake_case("thisIsATest")
        'this_is_a_test'
    """
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def pascal_case_to_snake_case(name: str) -> str:
    """
    Converts a PascalCase string to snake_case format.

    This function is a wrapper around camel_to_snake_case, as the same conversion
    rules apply to both PascalCase and camelCase strings.

    Args:
        name (str): The PascalCase string to convert (e.g., "MyVariableName").

    Returns:
        str: The snake_case version of the string (e.g., "my_variable_name").

    Example:
        >>> pascal_case_to_snake_case("ThisIsATest")
        'this_is_a_test'
    """
    return camel_to_snake_case(name=name)


def pascal_case_to_sentence(name: str) -> str:
    """
    Converts a PascalCase string to a capitalized sentence.

    This function splits a PascalCase string at word boundaries and spaces.
    - Preserves fully uppercase words (e.g., "BOB", "JSON")
    - Converts PascalCase components to lowercase (e.g., "LowKey" -> "low key")

    Args:
        name (str): The string to convert (e.g., "ThisIsATest" or "BOB LowKey").

    Returns:
        str: The formatted string with preserved uppercase words (e.g., "BOB low key").

    Example:
        >>> pascal_case_to_sentence("HelloWorld")
        'Hello world'
        >>> pascal_case_to_sentence("BOB LowKey")
        'BOB low key'
        >>> pascal_case_to_sentence("ParseJSONData")
        'Parse JSON data'
    """
    # First split by spaces
    space_parts: List[str] = name.split()
    result_parts: List[str] = []

    for part in space_parts:
        if part.isupper():
            # Preserve fully uppercase words
            result_parts.append(part)
        else:
            # Handle PascalCase parts
            words: List[str] = re.findall(r"([A-Z][a-z]+|[A-Z]{2,}(?=[A-Z][a-z]|\d|\W|$)|[A-Z]{2,}|[0-9]+)", part)
            processed_words: List[str] = [word if word.isupper() else word.lower() for word in words]
            result_parts.append(" ".join(processed_words))

    return " ".join(result_parts).capitalize()


def snake_to_pascal_case(snake_str: str) -> str:
    """
    Converts a snake_case string to PascalCase format.

    This function splits the string at underscores, capitalizes the first letter
    of each component, and joins them together without separators.

    Args:
        snake_str (str): The snake_case string to convert (e.g., "my_variable_name").

    Returns:
        str: The PascalCase version of the string (e.g., "MyVariableName").

    Example:
        >>> snake_to_pascal_case("hello_world")
        'HelloWorld'
    """
    components = snake_str.split("_")
    return "".join(component.title() for component in components)


def snake_to_capitalize_first_letter(snake_str: str) -> str:
    """
    Converts a snake_case string to a space-separated string with the first letter capitalized.

    This function splits the string at underscores, joins the components with spaces,
    and capitalizes only the first letter of the entire string.

    Args:
        snake_str (str): The snake_case string to convert (e.g., "hello_world").

    Returns:
        str: The space-separated string with first letter capitalized (e.g., "Hello world").

    Example:
        >>> snake_to_capitalize_first_letter("this_is_a_test")
        'This is a test'
    """
    components = snake_str.split("_")
    phrase = " ".join(components)
    return phrase.capitalize()


def is_snake_case(word: str) -> bool:
    return re.match(r"^[a-z][a-z0-9_]*$", word) is not None


def is_pascal_case(word: str) -> bool:
    return re.match(r"^[A-Z][a-zA-Z0-9]*$", word) is not None
