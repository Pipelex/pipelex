"""Dictionary utility functions for manipulating dictionary order and structure."""

from collections.abc import Callable
from typing import Any, TypeVar, cast

from pipelex import log
from pipelex.system.exceptions import NestedKeyConflictError

K = TypeVar("K")
V = TypeVar("V")


def insert_before(dictionary: dict[K, V], target_key: K, new_key: K, new_value: V) -> dict[K, V]:
    """Insert a new key-value pair before a target key in a dictionary.

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
    result: dict[K, V] = {}
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


def apply_to_strings_recursive(data: Any, transform_func: Callable[[str], str]) -> dict[str, Any]:
    """Recursively traverse a data structure and apply a transformation function to all string values.

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
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = apply_to_strings_recursive(value, transform_func)
        elif isinstance(value, list):
            list_value: list[Any] = cast("list[Any]", value)
            result[key] = apply_to_strings_in_list(list_value, transform_func)
        elif isinstance(value, str):
            result[key] = transform_func(value)
        else:
            # For all other types (int, float, bool, None, etc.), return as-is
            result[key] = value
    return result


def apply_to_strings_in_list(data: list[Any], transform_func: Callable[[str], str]) -> list[Any]:
    """Helper function to apply string transformation to items in a list."""
    result: list[Any] = []
    for item in data:
        if isinstance(item, dict):
            result.append(apply_to_strings_recursive(item, transform_func))
        elif isinstance(item, list):
            list_item: list[Any] = cast("list[Any]", item)
            result.append(apply_to_strings_in_list(list_item, transform_func))
        elif isinstance(item, str):
            result.append(transform_func(item))
        else:
            result.append(item)
    return result


def substitute_nested_in_context(context: dict[str, Any], extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Substitute nested values in context dict using dotted key notation.

    This function processes keys from extra_params that contain dots (e.g., "foo.bar.blip")
    and creates nested dictionary structures in the context dict. Keys without dots are
    added directly to the context.

    Args:
        context: The context dictionary to mutate
        extra_params: Dictionary with potentially dotted keys to process

    Returns:
        The mutated context dictionary

    Raises:
        NestedKeyConflictError: When attempting to create nested keys under a non-dict value

    Example:
        >>> context = {}
        >>> extra_params = {"foo.bar.blip": "hello"}
        >>> substitute_nested_in_context(context, extra_params)
        >>> context
        {'foo': {'bar': {'blip': 'hello'}}}

    """
    if not extra_params:
        return context

    original_context = context.copy()

    for key, value in extra_params.items():
        if "." not in key:
            # Simple key without dots - add directly to context
            context[key] = value
        else:
            # Dotted key - create nested structure
            segments = key.split(".")
            current = context

            # Navigate/create nested dicts for all segments except the last
            for segment in segments[:-1]:
                if segment not in current:
                    # Create new nested dict
                    current[segment] = {}
                elif not (hasattr(current[segment], "__getitem__") and hasattr(current[segment], "__setitem__")):
                    # Conflict: trying to nest under a non-dict-like value
                    # Must support both __getitem__ and __setitem__ to be dict-like (e.g., dict, StuffArtefact)
                    error_message = f"Cannot set nested key '{key}': '{segment}' is not a dict-like object"
                    log.error(original_context, title="original_context")
                    log.error(extra_params, title="extra_params")
                    raise NestedKeyConflictError(error_message)
                # Navigate into the nested dict
                current = current[segment]

            # Set the final value
            last_segment = segments[-1]
            current[last_segment] = value

    return context
