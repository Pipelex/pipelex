"""Dictionary utility functions for manipulating dictionary order and structure."""

from typing import Dict, TypeVar

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
