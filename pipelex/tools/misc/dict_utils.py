"""Dictionary utility functions for manipulating dictionary order and structure."""

from typing import Any, Callable, Dict, List, TypeVar, cast

K = TypeVar("K")
V = TypeVar("V")


def insert_before(dictionary: Dict[K, V], target_key: K, new_key: K, new_value: V) -> Dict[K, V]:
    """
    Insert a new key-value pair before a target key in a dictionary.

    Creates a new dictionary with the new item positioned before the target key.
    If the target key doesn't exist, the new item is added at the end.

    Args:
        dictionary: The source dictionary
        target_key: The key before which to insert the new item
        new_key: The new key to insert
        new_value: The new value to insert

    Returns:
        A new dictionary with the item inserted at the specified position

    Example:
        >>> d = {'a': 1, 'c': 3}
        >>> insert_before(d, 'c', 'b', 2)
        {'a': 1, 'b': 2, 'c': 3}
    """
    result: Dict[K, V] = {}
    inserted = False

    for key, value in dictionary.items():
        if key == target_key and not inserted:
            result[new_key] = new_value
            inserted = True
        result[key] = value

    # If target key wasn't found, add at the end
    if not inserted:
        result[new_key] = new_value

    return result


def apply_to_strings_recursive(data: Any, transform_func: Callable[[str], str]) -> Dict[str, Any]:
    """
    Recursively traverse a data structure and apply a transformation function to all string values.

    This function walks through dictionaries, lists, and other nested structures,
    applying the provided transformation function only to string values while
    preserving the original structure.

    Args:
        data: The data structure to traverse (dict, list, or any value)
        transform_func: Function to apply to each string value found

    Returns:
        A new data structure with the same shape but with transformed strings

    Example:
        >>> data = {'a': 'hello ${USER}', 'b': [1, 'world ${HOME}'], 'c': {'d': 'test ${PATH}'}}
        >>> result = apply_to_strings_recursive(data, lambda s: s.replace('${USER}', 'john'))
        >>> # Returns: {'a': 'hello john', 'b': [1, 'world ${HOME}'], 'c': {'d': 'test ${PATH}'}}
    """
    result: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = apply_to_strings_recursive(value, transform_func)
        elif isinstance(value, list):
            list_value: List[Any] = cast(List[Any], value)
            result[key] = apply_to_strings_in_list(list_value, transform_func)
        elif isinstance(value, str):
            result[key] = transform_func(value)
        else:
            # For all other types (int, float, bool, None, etc.), return as-is
            result[key] = value
    return result


def apply_to_strings_in_list(data: List[Any], transform_func: Callable[[str], str]) -> List[Any]:
    """Helper function to apply string transformation to items in a list."""
    result: List[Any] = []
    for item in data:
        if isinstance(item, dict):
            result.append(apply_to_strings_recursive(item, transform_func))
        elif isinstance(item, list):
            list_item: List[Any] = cast(List[Any], item)
            result.append(apply_to_strings_in_list(list_item, transform_func))
        elif isinstance(item, str):
            result.append(transform_func(item))
        else:
            result.append(item)
    return result
