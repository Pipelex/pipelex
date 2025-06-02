from typing import Any, List, Optional


def has_exactly_one_among_attributes_from_list(obj: Any, attributes_list: List[str]) -> bool:
    """
    Checks if exactly one attribute from a list of attributes is non-None in an object.

    This function is useful for validating mutually exclusive attributes in data models
    or configurations, ensuring that exactly one of the specified attributes has a value.

    Args:
        obj (Any): The object to check attributes on. Must support getattr().
        attributes_list (List[str]): List of attribute names to check.

    Returns:
        bool: True if exactly one attribute from the list is non-None,
              False otherwise.
    """
    provided_attributes = [attribute for attribute in attributes_list if getattr(obj, attribute) is not None]
    return len(provided_attributes) == 1


def has_more_than_one_among_attributes_from_list(obj: Any, attributes_list: List[str]) -> bool:
    """
    Checks if more than one attribute from a list of attributes is non-None in an object.

    This function is useful for detecting conflicts in configurations or data models
    where attributes are supposed to be mutually exclusive.

    Args:
        obj (Any): The object to check attributes on. Must support getattr().
        attributes_list (List[str]): List of attribute names to check.

    Returns:
        bool: True if more than one attribute from the list is non-None,
              False otherwise.
    """
    provided_attributes = [attribute for attribute in attributes_list if getattr(obj, attribute) is not None]
    return len(provided_attributes) > 1


def has_more_than_one_among_attributes_from_lists(obj: Any, attributes_lists: List[List[str]]) -> Optional[List[str]]:
    """
    Checks if more than one attribute from lists (plural) of attributes is non-None in an object.

    This function is useful for detecting conflicts in configurations or data models
    where attributes are supposed to be mutually exclusive.

    Args:
        obj (Any): The object to check attributes on. Must support getattr().
        attributes_lists (List[List[str]]): List of lists of attribute names to check.

    Returns:
        Optional[List[str]]: The list of attributes that are non-None if more than one, None otherwise.
    """
    for attributes_list in attributes_lists:
        if has_more_than_one_among_attributes_from_list(obj, attributes_list):
            return attributes_list
    return None
