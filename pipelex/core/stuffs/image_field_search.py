import types
import typing
from typing import Any

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent


def search_for_nested_image_fields(
    content_class: type[StuffContent],
    current_path: str = "",
) -> list[str]:
    """Recursively search for image fields in a structure class.

    Args:
        content_class: The StuffContent class to search
        current_path: Current field path being explored

    Returns:
        List of field paths that contain images
    """
    paths: list[str] = []

    # Iterate through all fields
    for field_name, field_info in content_class.model_fields.items():
        # Build the path for this field
        field_path = f"{current_path}.{field_name}" if current_path else field_name

        # Get the field type annotation
        field_type = field_info.annotation

        # Handle Optional types (Union with None)
        is_union = False
        union_args = None

        # Check for typing.Union (typing.Optional)
        is_typing_union = hasattr(field_type, "__origin__") and field_type.__origin__ is typing.Union  # type: ignore[union-attr] # pyright: ignore[reportOptionalMemberAccess]
        is_types_union = hasattr(types, "UnionType") and isinstance(field_type, types.UnionType)  # pyright: ignore[reportUnnecessaryIsInstance]
        if is_typing_union or is_types_union:
            is_union = True
            union_args = field_type.__args__  # type: ignore[union-attr]

        potential_types: list[Any] = []
        potential_field_types: list[Any] = []  # Keep track of the full type with generics
        if is_union and union_args:
            potential_types = list(union_args)
            potential_field_types = list(union_args)  # In union case, each arg is a complete type
        else:
            potential_types = [field_type]
            potential_field_types = [field_type]

        for idx, field_specific_type in enumerate(potential_types):
            # Get the corresponding field type with full generic info
            current_field_type = potential_field_types[idx]

            # Check if it's a list or tuple generic type (e.g., list[ImageContent], tuple[ImageContent, ...])
            if hasattr(field_specific_type, "__origin__") and field_specific_type.__origin__ in (list, tuple):  # type: ignore[union-attr]
                # Check if this container or its nested contents have images
                if check_generic_container_for_images(field_specific_type):
                    paths.append(field_path)
                continue  # Move to next field after handling list/tuple

            # Skip if field type is not a class
            if not isinstance(field_specific_type, type):
                continue
            if field_specific_type is type(None):
                continue

            # Try-except to handle Python 3.10 compatibility with generic types
            try:
                # Check if it's a direct ImageContent first
                if issubclass(field_specific_type, ImageContent):
                    paths.append(field_path)
                    continue

                # Check if it's a ListContent subclass (Pydantic creates actual classes, not generic aliases)
                if issubclass(field_specific_type, ListContent):
                    # For ListContent, check if the items have images
                    # Get the generic argument from Pydantic v2's __pydantic_generic_metadata__
                    list_item_types = None
                    if hasattr(field_specific_type, "__pydantic_generic_metadata__"):  # pyright: ignore[reportUnknownArgumentType]
                        # Pydantic v2 stores generic info as a dict
                        generic_metadata = field_specific_type.__pydantic_generic_metadata__  # type: ignore[attr-defined]
                        # generic_metadata is PydanticGenericMetadata which inherits from dict
                        if "args" in generic_metadata:  # pyright: ignore[reportUnnecessaryIsInstance]
                            list_item_types = generic_metadata["args"]
                    elif hasattr(current_field_type, "__args__"):
                        list_item_types = current_field_type.__args__  # type: ignore[union-attr]

                    if list_item_types:
                        has_images_in_list = False
                        for list_item_type in list_item_types:
                            if isinstance(list_item_type, type):
                                try:
                                    # Check if the item type is ImageContent
                                    if issubclass(list_item_type, ImageContent):
                                        has_images_in_list = True
                                        break
                                    # Check if the item type has nested images
                                    if issubclass(list_item_type, StuffContent) and not issubclass(list_item_type, ListContent):
                                        nested_paths = search_for_nested_image_fields(
                                            content_class=list_item_type,
                                            current_path="",
                                        )
                                        if nested_paths:
                                            has_images_in_list = True
                                            break
                                except TypeError:
                                    continue
                        if has_images_in_list:
                            paths.append(field_path)
                    continue

                # If it's a StuffContent subclass (excluding ListContent which we just handled), recurse into it
                if issubclass(field_specific_type, StuffContent):
                    nested_paths = search_for_nested_image_fields(
                        content_class=field_specific_type,
                        current_path=field_path,
                    )
                    paths.extend(nested_paths)
            except TypeError:
                # In Python 3.10, some generic types may pass isinstance(type) but fail issubclass()
                continue

    return paths


def check_generic_container_for_images(container_type: Any) -> bool:
    """Recursively check if a generic container type contains images at any depth.

    Handles nested generics like list[tuple[list[MediaCollection]]] with arbitrary depth.

    Args:
        container_type: A generic type like list[...], tuple[...]

    Returns:
        True if the container or its nested contents contain ImageContent
    """
    if not hasattr(container_type, "__origin__"):
        return False

    # Get the args (item types) from the generic
    container_args = getattr(container_type, "__args__", ())
    for arg_type in container_args:
        # Check if arg_type is itself a generic (nested list/tuple) - recurse!
        if hasattr(arg_type, "__origin__") and arg_type.__origin__ in (list, tuple):  # type: ignore[union-attr]
            if check_generic_container_for_images(arg_type):
                return True
        # Check if it's a regular type
        elif isinstance(arg_type, type):
            try:
                # Check if it's directly ImageContent
                if issubclass(arg_type, ImageContent):
                    return True
                # Check if it's a StuffContent that might have nested images
                if issubclass(arg_type, StuffContent) and not issubclass(arg_type, ListContent):
                    # Check if this type has nested image fields
                    nested_paths = search_for_nested_image_fields(
                        content_class=arg_type,
                        current_path="",
                    )
                    if nested_paths:
                        return True
            except TypeError:
                # Handle edge cases where issubclass fails
                continue
    return False
