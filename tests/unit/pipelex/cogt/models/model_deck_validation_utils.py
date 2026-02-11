"""Shared validation utilities for model deck testing.

These utilities validate model deck references (aliases, presets, waterfalls)
and are used by multiple test modules.
"""

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind


def find_invalid_alias_targets(
    aliases: dict[str, str],
    all_aliases: dict[str, str],
    all_waterfalls: dict[str, list[str]],
    known_model_handles: dict[str, ModelType],
    expected_model_type: ModelType,
) -> list[tuple[str, str, str]]:
    """Find aliases that reference invalid targets.

    Args:
        aliases: The aliases dict to validate
        all_aliases: All available aliases for this model type
        all_waterfalls: All available waterfalls for this model type
        known_model_handles: Mapping of model handle -> ModelType
        expected_model_type: The expected model type for this deck (LLM, TEXT_EXTRACTOR, IMG_GEN)

    Returns:
        List of (alias_name, target_value, reason) tuples for invalid references
    """
    invalid_refs: list[tuple[str, str, str]] = []

    for alias_name, target_value in aliases.items():
        ref = ModelReference.parse(target_value)

        match ref.kind:
            case ModelReferenceKind.ALIAS:
                if ref.name not in all_aliases:
                    invalid_refs.append((alias_name, target_value, f"alias '{ref.name}' not found"))
            case ModelReferenceKind.WATERFALL:
                if ref.name not in all_waterfalls:
                    invalid_refs.append((alias_name, target_value, f"waterfall '{ref.name}' not found"))
            case ModelReferenceKind.PRESET:
                invalid_refs.append((alias_name, target_value, "aliases cannot reference presets ($ prefix)"))
            case ModelReferenceKind.HANDLE:
                if ref.name not in known_model_handles:
                    invalid_refs.append((alias_name, target_value, f"model handle '{ref.name}' not found in backends"))
                elif known_model_handles[ref.name] != expected_model_type:
                    actual_type = known_model_handles[ref.name]
                    invalid_refs.append(
                        (alias_name, target_value, f"model handle '{ref.name}' has type '{actual_type}' but expected '{expected_model_type}'")
                    )

    return invalid_refs


def find_invalid_waterfall_entries(
    waterfalls: dict[str, list[str]],
    all_aliases: dict[str, str],
    known_model_handles: dict[str, ModelType],
    expected_model_type: ModelType,
) -> list[tuple[str, int, str, str]]:
    """Find waterfall entries that reference invalid targets.

    Args:
        waterfalls: The waterfalls dict to validate
        all_aliases: All available aliases for this model type
        known_model_handles: Mapping of model handle -> ModelType
        expected_model_type: The expected model type for this deck (LLM, TEXT_EXTRACTOR, IMG_GEN)

    Returns:
        List of (waterfall_name, index, entry_value, reason) tuples for invalid entries
    """
    invalid_refs: list[tuple[str, int, str, str]] = []

    for waterfall_name, entries in waterfalls.items():
        # Empty waterfalls cause IndexError at runtime (fallback_list[0])
        if not entries:
            invalid_refs.append((waterfall_name, -1, "", "waterfall cannot be empty"))
            continue

        for index, entry_value in enumerate(entries):
            ref = ModelReference.parse(entry_value)

            match ref.kind:
                case ModelReferenceKind.ALIAS:
                    if ref.name not in all_aliases:
                        invalid_refs.append((waterfall_name, index, entry_value, f"alias '{ref.name}' not found"))
                case ModelReferenceKind.WATERFALL:
                    invalid_refs.append((waterfall_name, index, entry_value, "waterfalls cannot contain other waterfalls (~ prefix)"))
                case ModelReferenceKind.PRESET:
                    invalid_refs.append((waterfall_name, index, entry_value, "waterfalls cannot contain presets ($ prefix)"))
                case ModelReferenceKind.HANDLE:
                    if ref.name not in known_model_handles:
                        invalid_refs.append((waterfall_name, index, entry_value, f"model handle '{ref.name}' not found in backends"))
                    elif known_model_handles[ref.name] != expected_model_type:
                        actual_type = known_model_handles[ref.name]
                        invalid_refs.append(
                            (
                                waterfall_name,
                                index,
                                entry_value,
                                f"model handle '{ref.name}' has type '{actual_type}' but expected '{expected_model_type}'",
                            )
                        )

    return invalid_refs


def find_circular_aliases(
    aliases: dict[str, str],
) -> list[tuple[str, list[str]]]:
    """Find circular alias chains.

    Args:
        aliases: The aliases dict to check for cycles

    Returns:
        List of (starting_alias, cycle_path) tuples for detected cycles
    """
    cycles: list[tuple[str, list[str]]] = []

    for start_alias in aliases:
        visited: list[str] = []
        current = start_alias

        while current in aliases:
            if current in visited:
                cycle_start_idx = visited.index(current)
                cycle_path = [*visited[cycle_start_idx:], current]
                if start_alias in cycle_path:
                    cycles.append((start_alias, cycle_path))
                break

            visited.append(current)
            target = aliases[current]
            ref = ModelReference.parse(target)

            match ref.kind:
                case ModelReferenceKind.ALIAS:
                    # Explicit alias reference (@name or alias:name)
                    current = ref.name
                case ModelReferenceKind.HANDLE:
                    # Unprefixed reference - follow if it's an alias key (matches runtime behavior)
                    if ref.name in aliases:
                        current = ref.name
                    else:
                        break
                case ModelReferenceKind.WATERFALL | ModelReferenceKind.PRESET:
                    # Waterfalls and presets don't continue the alias chain
                    break

    unique_cycles: list[tuple[str, list[str]]] = []
    seen_cycles: set[frozenset[str]] = set()

    for start_alias, cycle_path in cycles:
        cycle_set = frozenset(cycle_path)
        if cycle_set not in seen_cycles:
            seen_cycles.add(cycle_set)
            unique_cycles.append((start_alias, cycle_path))

    return unique_cycles
