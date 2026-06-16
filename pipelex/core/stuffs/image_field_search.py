import types
import typing
from typing import Any

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent


def _is_union_type(type_hint: Any) -> bool:
    """Return True when the annotation is a Union/Optional."""
    is_typing_union = hasattr(type_hint, "__origin__") and type_hint.__origin__ is typing.Union  # type: ignore[union-attr] # pyright: ignore[reportOptionalMemberAccess]
    is_types_union = hasattr(types, "UnionType") and isinstance(type_hint, types.UnionType)  # pyright: ignore[reportUnnecessaryIsInstance]
    return is_typing_union or is_types_union


def _get_list_content_item_types(list_content_type: Any) -> tuple[Any, ...]:
    """Return the item types stored in a ListContent annotation or subclass."""
    if hasattr(list_content_type, "__pydantic_generic_metadata__"):  # pyright: ignore[reportUnknownArgumentType]
        generic_metadata = list_content_type.__pydantic_generic_metadata__  # type: ignore[attr-defined]
        if "args" in generic_metadata:  # pyright: ignore[reportUnnecessaryIsInstance]
            return tuple(generic_metadata["args"])

    return tuple(getattr(list_content_type, "__args__", ()))


def _annotation_contains_images(type_hint: Any) -> bool:
    """Return True when an annotation contains images directly or indirectly."""
    if type_hint is Ellipsis or type_hint is type(None):
        return False

    if _is_union_type(type_hint):
        union_args = getattr(type_hint, "__args__", ())
        return any(_annotation_contains_images(arg_type) for arg_type in union_args)

    origin = getattr(type_hint, "__origin__", None)
    if origin in {list, tuple, dict}:
        return check_generic_container_for_images(type_hint)
    if origin is ListContent:
        return any(_annotation_contains_images(arg_type) for arg_type in getattr(type_hint, "__args__", ()))

    if not isinstance(type_hint, type):
        return False

    try:
        if issubclass(type_hint, ImageContent):
            return True
        if issubclass(type_hint, ListContent):
            return any(_annotation_contains_images(arg_type) for arg_type in _get_list_content_item_types(type_hint))
        if issubclass(type_hint, StuffContent):
            return bool(
                search_for_nested_image_fields(
                    content_class=type_hint,
                    current_path="",
                )
            )
    except TypeError:
        return False

    return False


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
        is_union = _is_union_type(field_type)
        union_args = field_type.__args__ if is_union else None  # type: ignore[union-attr]

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

            # Check if it's a generic container type.
            # Example: list[ImageContent], tuple[ImageContent, ...], dict[str, ImageContent].
            origin = getattr(field_specific_type, "__origin__", None)
            if origin in {list, tuple, dict, ListContent}:
                # Check if this container or its nested contents have images.
                if _annotation_contains_images(field_specific_type):
                    paths.append(field_path)
                continue  # Move to next field after handling generic containers

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
                    list_item_types = _get_list_content_item_types(field_specific_type)
                    if not list_item_types and hasattr(current_field_type, "__args__"):
                        list_item_types = tuple(current_field_type.__args__)  # type: ignore[union-attr]

                    if any(_annotation_contains_images(list_item_type) for list_item_type in list_item_types):
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

    Handles nested generics like list[tuple[list[MediaCollection]]] or
    dict[str, list[ImageContent]] with arbitrary depth.

    Args:
        container_type: A generic type like list[...], tuple[...], dict[..., ...]

    Returns:
        True if the container or its nested contents contain ImageContent
    """
    if not hasattr(container_type, "__origin__"):
        return False

    origin = getattr(container_type, "__origin__", None)
    container_args = getattr(container_type, "__args__", ())

    if origin is dict:
        if len(container_args) < 2:
            return False
        return _annotation_contains_images(container_args[1])

    return any(_annotation_contains_images(arg_type) for arg_type in container_args)
