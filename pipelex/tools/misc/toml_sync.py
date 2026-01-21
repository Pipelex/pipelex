"""TOML synchronization utilities with comment preservation."""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, Field
from tomlkit import TOMLDocument
from tomlkit.items import Item, Table

from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class TomlKeyChange(BaseModel):
    """Represents a single key change during TOML sync."""

    key_path: str
    old_value: Any
    new_value: Any


class TomlSyncResult(BaseModel):
    """Result of a TOML sync operation."""

    updated_keys: list[str] = Field(default_factory=list)
    unchanged_keys: list[str] = Field(default_factory=list)
    changes: list[TomlKeyChange] = Field(default_factory=empty_list_factory_of(TomlKeyChange))

    @property
    def updated_count(self) -> int:
        return len(self.updated_keys)

    @property
    def unchanged_count(self) -> int:
        return len(self.unchanged_keys)


def get_nested_value(doc: TOMLDocument | Table | dict[str, Any], key_path: str) -> tuple[bool, Any]:
    """Traverse TOML document by key path (dot-separated).

    Args:
        doc: TOML document or table to traverse
        key_path: Dot-separated key path (e.g., "section.subsection.key")

    Returns:
        Tuple of (found, value) where found is True if key exists
    """
    keys = key_path.split(".")
    current: Any = doc

    for key in keys:
        if isinstance(current, (dict, TOMLDocument, Table)):
            if key in current:
                next_value: Any = current[key]  # type: ignore[assignment]
                current = next_value  # pyright: ignore[reportUnknownVariableType]
            else:
                return False, None
        else:
            return False, None

    result_value: Any = current  # pyright: ignore[reportUnknownVariableType]
    return True, result_value  # pyright: ignore[reportUnknownVariableType]


def set_nested_value(doc: TOMLDocument | Table | dict[str, Any], key_path: str, value: Any) -> bool:
    """Set value in TOML document by key path (dot-separated).

    Only sets the value if the key already exists. Preserves inline comments
    (trivia) from the existing item when updating the value.

    Args:
        doc: TOML document or table to modify
        key_path: Dot-separated key path (e.g., "section.subsection.key")
        value: Value to set

    Returns:
        True if the key was found and set, False otherwise
    """
    keys = key_path.split(".")
    current: Any = doc

    # Navigate to the parent of the target key
    for key in keys[:-1]:
        if isinstance(current, (dict, TOMLDocument, Table)):
            if key in current:
                next_value: Any = current[key]  # type: ignore[assignment]
                current = next_value  # pyright: ignore[reportUnknownVariableType]
            else:
                return False
        else:
            return False

    # Set the final key if it exists
    final_key = keys[-1]
    if isinstance(current, (dict, TOMLDocument, Table)) and final_key in current:
        # Capture existing item's trivia (inline comments) before replacing
        existing_item: Any = current[final_key]  # type: ignore[assignment]
        existing_trivia = None
        if isinstance(existing_item, Item):
            existing_trivia = existing_item.trivia

        # Set the new value
        current[final_key] = value

        # Restore the trivia from the old item to preserve inline comments
        if existing_trivia is not None:
            new_item: Any = current[final_key]  # type: ignore[assignment]
            if isinstance(new_item, Item):
                new_item._trivia = existing_trivia  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        return True

    return False


def collect_leaf_key_paths(doc: TOMLDocument | Table | dict[str, Any], prefix: str = "") -> list[str]:
    """Collect all leaf node key paths from a TOML document.

    Args:
        doc: TOML document or table to traverse
        prefix: Current key path prefix (used in recursion)

    Returns:
        List of dot-separated key paths to all leaf nodes
    """
    paths: list[str] = []

    # Cast doc.items() to work around tomlkit's incomplete type annotations
    items: list[tuple[str, Any]] = list(doc.items())  # type: ignore[arg-type]
    for key, value in items:
        current_path = f"{prefix}.{key}" if prefix else key

        if isinstance(value, (dict, Table)):
            # Recurse into nested tables
            nested_doc: dict[str, Any] = cast("dict[str, Any]", value)
            paths.extend(collect_leaf_key_paths(nested_doc, current_path))
        else:
            # This is a leaf node
            paths.append(current_path)

    return paths


def sync_toml_values(source_path: str, target_path: str, dry_run: bool = False) -> TomlSyncResult:
    """Sync values from source TOML to target TOML, preserving target's structure and comments.

    For each leaf key in the target:
    - If the key exists in source: update with source value
    - If the key doesn't exist in source: keep target value as-is

    Args:
        source_path: Path to the source TOML file (values come from here)
        target_path: Path to the target TOML file (structure preserved, values updated)
        dry_run: If True, don't write changes, just return what would change

    Returns:
        TomlSyncResult with lists of updated and unchanged keys, plus detailed changes
    """
    source_doc = load_toml_with_tomlkit(source_path)
    target_doc = load_toml_with_tomlkit(target_path)

    result = TomlSyncResult()

    # Get all leaf keys from target document
    target_keys = collect_leaf_key_paths(target_doc)

    for key_path in target_keys:
        source_found, source_value = get_nested_value(source_doc, key_path)
        target_found, target_value = get_nested_value(target_doc, key_path)

        if not target_found:
            # Should not happen since we got keys from target, but be safe
            continue

        if source_found:
            if source_value != target_value:
                # Value differs, update it
                if not dry_run:
                    set_nested_value(target_doc, key_path, source_value)
                result.updated_keys.append(key_path)
                result.changes.append(
                    TomlKeyChange(
                        key_path=key_path,
                        old_value=target_value,
                        new_value=source_value,
                    )
                )
            else:
                # Value is the same
                result.unchanged_keys.append(key_path)
        else:
            # Key doesn't exist in source, keep target value
            result.unchanged_keys.append(key_path)

    # Save if not dry run and there were changes
    if not dry_run and result.updated_keys:
        save_toml_to_path(target_doc, target_path)

    return result
