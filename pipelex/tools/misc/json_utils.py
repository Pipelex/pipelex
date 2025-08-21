import json
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union, cast

from kajson import kajson
from pydantic import BaseModel

from pipelex.tools.exceptions import ToolException
from pipelex.tools.misc.file_utils import save_text_to_path
from pipelex.tools.typing.pydantic_utils import CustomBaseModel

JsonContent = Union[Dict[str, Any], List[Any]]


class ArgumentTypeError(ToolException):
    pass


class JsonTypeError(ToolException):
    pass


def json_str(some_object: Any, title: Optional[str] = None, is_spaced: bool = False) -> str:
    """
    Creates a formatted JSON string representation of any Python object with optional title and spacing.

    This function is a higher-level wrapper around purify_json that provides additional formatting
    options. It always uses 4-space indentation and disables warning wrapping for non-serializable
    data.

    Args:
        some_object (Any): The object to convert to a JSON string. Can be any type supported
            by purify_json.
        title (Optional[str], optional): A title to prepend to the JSON string. If provided,
            the output will be in the format "title: {json_string}". Defaults to None.
        is_spaced (bool, optional): If True, adds newlines before and after the JSON string
            for better readability. Defaults to False.

    Returns:
        str: The formatted JSON string representation of the object.

    Example:
        >>> data = {"name": "test", "values": [1, 2, 3]}
        >>> print(json_str(data, title="Data", is_spaced=True))

        Data: {
            "name": "test",
            "values": [1, 2, 3]
        }

    """
    _, json_string = purify_json(some_object, indent=4, is_warning_enabled=False)
    if title:
        json_string = f"{title}: {json_string}"
    if is_spaced:
        json_string = f"\n{json_string}\n"
    return json_string


def save_as_json_to_path(
    object_to_save: Any,
    path: str,
    indent: Optional[int] = 4,
    is_warning_enabled: bool = True,
):
    """
    Saves a Python object as a JSON file at the specified path.

    This function converts a Python object to a JSON string and saves it to a file. The object
    is first purified to ensure JSON compatibility before saving.

    Args:
        object_to_save (Any): The Python object to be saved as JSON. Can be any JSON-serializable object.
        path (str): The file path where the JSON file will be saved.
        indent (Optional[int], optional): Number of spaces for JSON formatting indentation. Defaults to 4.
        is_warning_enabled (bool, optional): Whether to show warnings during JSON purification. Defaults to True.

    Returns:
        None
    """
    _, json_string = purify_json(object_to_save, indent=indent, is_warning_enabled=is_warning_enabled)
    save_text_to_path(json_string, path)


def load_json_from_path(path: str) -> JsonContent:
    """
    Loads and parses a JSON file from the specified path.

    This function reads a JSON file and returns its contents as a Python object.
    The file is read using UTF-8 encoding.

    Args:
        path (str): The file path to the JSON file to be loaded.

    Returns:
        JsonContent: The parsed JSON content as a Python object (can be a dict, list, string, number, bool, or None).

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    with open(path, encoding="utf-8") as file:
        json_content: JsonContent = json.load(file)
        return json_content


def load_json_dict_from_path(path: str) -> Dict[Any, Any]:
    """
    Loads a JSON file and ensures it contains a dictionary.

    This function reads a JSON file and verifies that its content is a dictionary.
    It uses load_json_from_path internally and adds type checking.

    Args:
        path (str): The file path to the JSON file to be loaded.

    Returns:
        Dict[Any, Any]: The parsed JSON content as a Python dictionary.

    Raises:
        JsonTypeError: If the JSON content is not a dictionary.
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    json_content: JsonContent = load_json_from_path(path)
    if isinstance(json_content, dict):
        return json_content
    else:
        raise JsonTypeError(f"{path} is not a dict")


def load_json_list_from_path(path: str) -> List[Any]:
    """
    Loads a JSON file and ensures it contains a list.

    This function reads a JSON file and verifies that its content is a list.
    It uses load_json_from_path internally and adds type checking.

    Args:
        path (str): The file path to the JSON file to be loaded.

    Returns:
        List[Any]: The parsed JSON content as a Python list.

    Raises:
        JsonTypeError: If the JSON content is not a list.
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    json_content: JsonContent = load_json_from_path(path)
    if isinstance(json_content, list):
        return json_content
    else:
        raise JsonTypeError(f"{path} is not a list")


def deep_update(target_dict: Dict[str, Any], updates: Dict[str, Any]):
    """
    Recursively updates a dictionary with values from another dictionary.

    This function performs a deep merge of two dictionaries, handling nested
    dictionaries and lists. For dictionaries, it recursively updates values,
    and for lists, it concatenates them.

    Args:
        target_dict (Dict[str, Any]): The dictionary to update. This dictionary
            will be modified in place.
        updates (Dict[str, Any]): The dictionary containing updates to apply.

    Example:
        >>> base = {"a": 1, "b": {"x": 2, "y": 3}, "c": [1, 2]}
        >>> updates = {"b": {"y": 4, "z": 5}, "c": [3, 4]}
        >>> deep_update(base, updates)
        >>> print(base)
        {'a': 1, 'b': {'x': 2, 'y': 4, 'z': 5}, 'c': [1, 2, 3, 4]}
    """
    for key, value in updates.items():
        if isinstance(value, dict) and key in target_dict and isinstance(target_dict[key], dict):
            deep_update(target_dict[key], value)  # type: ignore
        elif isinstance(value, list) and key in target_dict and isinstance(target_dict[key], list):
            target_dict[key] = list(target_dict[key] + value)  # type: ignore
        else:
            target_dict[key] = value


def remove_none_values(json_content: JsonContent | Any) -> JsonContent | Any:
    """
    Recursively removes all None values from a JSON-compatible data structure.

    This function traverses dictionaries and lists, removing any keys with None values
    from dictionaries and processing nested structures. It preserves the structure of
    the input while cleaning out None values at any depth.

    Args:
        json_content (JsonContent): The JSON-compatible data structure (dict or list)
            to process. Can contain nested dictionaries and lists.

    Returns:
        JsonContent: A new data structure of the same type as the input, but with all
            None values removed from dictionaries at any level of nesting.

    Example:
        >>> data = {
        ...     "name": "test",
        ...     "value": None,
        ...     "nested": {"key": "exists", "empty": None},
        ...     "list": [1, None, {"key": None}]
        ... }
        >>> result = remove_none_values(data)
        >>> print(result)
        {
            "name": "test",
            "nested": {"key": "exists"},
            "list": [1, {}]
        }
    """
    if isinstance(json_content, dict):
        json_content = cast(Dict[str, Any], json_content)  # pyright: ignore[reportUnnecessaryCast]
        cleaned_dict: Dict[str, Any] = {}
        for key, value in json_content.items():
            if value is not None:
                cleaned_dict[key] = remove_none_values(json_content=value)
        return cleaned_dict
    elif isinstance(json_content, list):
        json_content = cast(List[Any], json_content)  # pyright: ignore[reportUnnecessaryCast]
        return [remove_none_values(item) for item in json_content]
    else:
        return json_content


def remove_none_values_from_dict(data: Mapping[str, Any]) -> Dict[str, Any]:
    processed = remove_none_values(json_content=data)
    if not isinstance(processed, dict):
        raise JsonTypeError("Removing None values from a dict, we expected a dict in return")
    processed = cast(Dict[str, Any], processed)  # pyright: ignore[reportUnnecessaryCast]
    return processed


def purify_json(
    data: Any,
    indent: Optional[int] = None,
    is_truncate_bytes_enabled: bool = False,
    is_warning_enabled: bool = True,
) -> Tuple[Union[Dict[Any, Any], List[Any]], str]:
    """
    Converts any Python object into a JSON-serializable format and its string representation.

    This function handles various types of input data:
    - Pydantic BaseModel instances are converted using their model_dump method
    - Lists of BaseModel instances are converted element by element
    - Other types are attempted to be JSON serialized directly
    - If standard JSON serialization fails, it attempts using kajson or falls back to str conversion

    Args:
        data (Any): The data to convert. Can be a Pydantic model, list, dict, or any other type.
        indent (Optional[int], optional): Number of spaces for JSON formatting indentation. Defaults to None.
        is_warning_enabled (bool, optional): If True, wraps non-serializable data in a warning object.
            Defaults to True.

    Returns:
        Tuple[Union[Dict[Any, Any], List[Any]], str]: A tuple containing:
            - The purified data structure (either a dict or list)
            - The JSON string representation of the data

    Example:
        >>> model = SomeModel(name="test")
        >>> data, json_str = purify_json(model)
        >>> print(json_str)
        '{"name": "test"}'
    """
    dict_string: str
    if isinstance(data, CustomBaseModel) and is_truncate_bytes_enabled:
        return purify_json(
            data.model_dump_truncated(serialize_as_any=True),
            indent=indent,
            is_truncate_bytes_enabled=is_truncate_bytes_enabled,
            is_warning_enabled=is_warning_enabled,
        )
    elif isinstance(data, BaseModel):
        return purify_json(
            data.model_dump(serialize_as_any=True),
            indent=indent,
            is_truncate_bytes_enabled=is_truncate_bytes_enabled,
            is_warning_enabled=is_warning_enabled,
        )

    if isinstance(data, list):
        the_list = data  # type: ignore
        if not the_list:
            return [], "[]"
        if isinstance(the_list[0], CustomBaseModel) and is_truncate_bytes_enabled:
            the_list_of_custom_base_models: List[CustomBaseModel] = the_list
            pure_list = [item.model_dump_truncated(serialize_as_any=True) for item in the_list_of_custom_base_models]
            dict_string = json.dumps(pure_list, indent=indent, default=str)
            return pure_list, dict_string
        elif isinstance(the_list[0], BaseModel):
            the_list_of_base_models: List[BaseModel] = the_list
            pure_list = [item.model_dump(serialize_as_any=True) for item in the_list_of_base_models]
            dict_string = json.dumps(pure_list, indent=indent, default=str)
            return pure_list, dict_string

    try:
        dict_string = json.dumps(data, indent=indent)
        pure_dict: Union[Dict[Any, Any], List[Any]] = data
    except TypeError:
        try:
            dict_string = kajson.dumps(data, indent=indent)  # pyright: ignore[reportUnknownMemberType]
        except Exception:
            if is_warning_enabled:
                data = {"!": data}
            dict_string = json.dumps(data, indent=indent, default=str)
        pure_dict = json.loads(dict_string)
    return pure_dict, dict_string


def purify_json_list(
    data: List[Any],
    indent: Optional[int] = None,
    is_truncate_bytes_enabled: bool = False,
) -> Tuple[List[Any], str]:
    """
    Converts a list of Python objects into a JSON-serializable list and its string representation.

    This function specifically handles lists and provides specialized processing for lists of
    Pydantic BaseModel instances. It attempts multiple serialization methods to ensure successful
    conversion.

    Args:
        data (List[Any]): The list to convert. Can contain Pydantic models or other types.
        indent (Optional[int], optional): Number of spaces for JSON formatting indentation.
            Defaults to None.

    Returns:
        Tuple[List[Any], str]: A tuple containing:
            - The purified list with JSON-serializable elements
            - The JSON string representation of the list

    Example:
        >>> models = [SomeModel(name="test1"), SomeModel(name="test2")]
        >>> data, json_str = purify_json_list(models)
        >>> print(json_str)
        '[{"name": "test1"}, {"name": "test2"}]'
    """
    list_string: str
    pure_list: List[Any]

    if not data:
        return [], "[]"
    if isinstance(data[0], CustomBaseModel) and is_truncate_bytes_enabled:
        the_list_of_custom_base_models: List[CustomBaseModel] = data
        pure_list = [item.model_dump_truncated(serialize_as_any=True) for item in the_list_of_custom_base_models]
        list_string = json.dumps(pure_list, indent=indent, default=str)
        return pure_list, list_string
    elif isinstance(data[0], BaseModel):
        the_list_of_base_models: List[BaseModel] = data
        pure_list = [item.model_dump(serialize_as_any=True) for item in the_list_of_base_models]
        list_string = json.dumps(pure_list, indent=indent, default=str)
        return pure_list, list_string

    try:
        list_string = json.dumps(data, indent=indent)
        pure_list = data
    except TypeError:
        try:
            list_string = kajson.dumps(data, indent=indent)  # pyright: ignore[reportUnknownMemberType]
        except Exception:
            list_string = json.dumps(data, indent=indent, default=str)
        pure_list = json.loads(list_string)
    return pure_list, list_string


def purify_json_dict(data: Any, indent: Optional[int] = None, is_warning_enabled: bool = True) -> Tuple[Dict[str, Any], str]:
    """
    Converts any Python object into a JSON-serializable dictionary and its string representation.

    This function specifically handles dictionary-like objects and Pydantic BaseModel instances,
    converting them to pure dictionaries that can be JSON serialized. It includes multiple
    fallback mechanisms for handling non-standard JSON types.

    Args:
        data (Any): The data to convert. Can be a Pydantic model or dictionary-like object.
        indent (Optional[int], optional): Number of spaces for JSON formatting indentation.
            Defaults to None.
        is_warning_enabled (bool, optional): If True, wraps non-serializable data in a warning
            object with a "!" key. Defaults to True.

    Returns:
        Tuple[Dict[str, Any], str]: A tuple containing:
            - The purified dictionary with JSON-serializable values
            - The JSON string representation of the dictionary

    Raises:
        ArgumentTypeError: If the input data is a list instead of a dictionary-like object.

    Example:
        >>> model = SomeModel(name="test", value=123)
        >>> data, json_str = purify_json_dict(model)
        >>> print(json_str)
        '{"name": "test", "value": 123}'
    """
    dict_string: str
    if isinstance(data, BaseModel):
        return purify_json_dict(
            data.model_dump(serialize_as_any=True),
            indent=indent,
            is_warning_enabled=is_warning_enabled,
        )

    if isinstance(data, list):
        raise ArgumentTypeError("The data is a list, not a dict")

    try:
        dict_string = json.dumps(data, indent=indent)
        pure_dict: Dict[str, Any] = data
    except TypeError:
        try:
            dict_string = kajson.dumps(data, indent=indent)  # pyright: ignore[reportUnknownMemberType]
        except Exception:
            if is_warning_enabled:
                data = {"!": data}
            dict_string = json.dumps(data, indent=indent, default=str)
        pure_dict = json.loads(dict_string)
    return pure_dict, dict_string


def pure_json_str(data: Any, indent: Optional[int] = None, is_warning_enabled: bool = True) -> str:
    """
    Converts any Python object directly to its JSON string representation.

    This is a convenience wrapper around purify_json that returns only the string
    representation, discarding the intermediate data structure. It inherits all the
    type handling capabilities of purify_json.

    Args:
        data (Any): The data to convert to a JSON string. Can be any type supported
            by purify_json.
        indent (Optional[int], optional): Number of spaces for JSON formatting indentation.
            Defaults to None.
        is_warning_enabled (bool, optional): If True, wraps non-serializable data in a
            warning object. Defaults to True.

    Returns:
        str: The JSON string representation of the data.

    Example:
        >>> model = SomeModel(name="test")
        >>> json_str = pure_json_str(model, indent=2)
        >>> print(json_str)
        '{
          "name": "test"
        }'
    """
    _, json_string = purify_json(data, indent=indent, is_warning_enabled=is_warning_enabled)
    return json_string
