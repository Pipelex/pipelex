"""Reconstruct a Pydantic BaseModel class from a JSON schema using datamodel-code-generator.

This module is the bridge between JSON schema (from model_json_schema()) and a live
BaseModel class that can be used as a structured output schema for LLM generation.
The generated class carries its own source code as __kajson_class_source__, enabling
kajson to deserialize it across process boundaries without a class registry.

Security: this module exec()'s code generated from an attacker-influenceable JSON schema
when schemas cross a process boundary (e.g. Temporal payloads), so two layers of defense
are applied — see _reject_unsafe_schema_extensions and _make_restricted_import below.
"""

import builtins
import hashlib
import json
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from pipelex.cogt.content_generation.exceptions import UnsafeSchemaError

_schema_cache: dict[str, type[BaseModel]] = {}
_cache_lock = threading.Lock()


def model_class_from_json_schema(schema: dict[str, Any], class_name: str) -> type[BaseModel]:
    """Reconstruct a BaseModel class from a JSON schema dict.

    Args:
        schema: The JSON schema as returned by SomeModel.model_json_schema().
        class_name: The expected class name (must match the schema's title).

    Returns:
        A BaseModel subclass with __kajson_class_source__ attached.
    """
    cache_key = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()

    with _cache_lock:
        if cache_key in _schema_cache:
            return _schema_cache[cache_key]

    source_code = _generate_source_from_schema(schema)
    reconstructed_class = _exec_and_extract_class(source_code, class_name)
    reconstructed_class.__kajson_class_source__ = source_code  # type: ignore[attr-defined]

    with _cache_lock:
        if cache_key in _schema_cache:
            return _schema_cache[cache_key]
        _schema_cache[cache_key] = reconstructed_class

    return reconstructed_class


def _normalize_class_name(title: str) -> str:
    """Convert a schema title to a PascalCase class name (matching datamodel-code-generator behavior).

    Splits on non-alphanumeric sequences, capitalizes the first char of each segment,
    and preserves existing capitalization within segments (unlike str.title() which
    lowercases everything after the first char).
    """
    segments = re.split(r"[^A-Za-z0-9]+", title)
    return "".join(segment[0].upper() + segment[1:] if segment else "" for segment in segments)


_UNSAFE_EXTENSION_PREFIX = "x-python-"


def _collect_unsafe_extension_paths(node: Any, path: str, found: list[str]) -> None:
    """Walk a JSON-schema-shaped value, collecting dotted paths to any x-python-* key.

    These extensions cause datamodel-code-generator to emit arbitrary `from X import Y`
    statements with no sanitization, which is a code-injection primitive on any path
    where the schema crosses an untrusted boundary (e.g. Temporal payloads).
    """
    if isinstance(node, dict):
        node_dict = cast("dict[str, Any]", node)
        for key, value in node_dict.items():
            child_path = f"{path}.{key}" if path else key
            if key.startswith(_UNSAFE_EXTENSION_PREFIX):
                found.append(child_path)
            _collect_unsafe_extension_paths(value, child_path, found)
    elif isinstance(node, list):
        node_list = cast("list[Any]", node)
        for index, item in enumerate(node_list):
            _collect_unsafe_extension_paths(item, f"{path}[{index}]", found)


def _reject_unsafe_schema_extensions(schema: dict[str, Any]) -> None:
    """Raise UnsafeSchemaError if the schema contains any x-python-* codegen extension.

    Layer 1 of the schema_to_model security perimeter: kill the known exploit primitive
    at the source rather than scrubbing it silently — silent stripping would turn a
    malicious payload into a successful run with the attacker's payload merely ignored,
    leaving no signal in logs for incident response.
    """
    found: list[str] = []
    _collect_unsafe_extension_paths(schema, "", found)
    if found:
        msg = f"Unsafe codegen extensions found in schema: {found}"
        raise UnsafeSchemaError(msg)


def _generate_source_from_schema(schema: dict[str, Any]) -> str:
    """Generate Python source code from a JSON schema using datamodel-code-generator."""
    from datamodel_code_generator import InputFileType, generate  # noqa: PLC0415
    from datamodel_code_generator.enums import DataModelType  # noqa: PLC0415

    _reject_unsafe_schema_extensions(schema)

    schema_str = json.dumps(schema)

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
        output_path = Path(tmp.name)

    try:
        generate(
            input_=schema_str,
            input_file_type=InputFileType.JsonSchema,
            output=output_path,
            output_model_type=DataModelType.PydanticV2BaseModel,
        )
        return output_path.read_text(encoding="utf-8")
    finally:
        output_path.unlink(missing_ok=True)


_BLOCKED_BUILTINS = frozenset({"eval", "exec", "compile", "open", "input", "breakpoint", "exit", "quit"})

_ALLOWED_IMPORT_TOP_LEVELS = frozenset(
    {
        "pydantic",
        "typing",
        "typing_extensions",
        "enum",
        "datetime",
        "decimal",
        "uuid",
        "__future__",
        "collections",
        "re",
    }
)


def _restricted_import(
    name: str,
    import_globals: dict[str, Any] | None = None,
    import_locals: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] | None = (),
    level: int = 0,
) -> Any:
    """Replacement for builtin __import__ that allows only an allowlist of modules.

    Layer 2 of the schema_to_model security perimeter: even if a future codegen feature
    in datamodel-code-generator emits new imports, this wrapper keeps the exec namespace
    constrained to what the generator's output legitimately requires. The intended
    failure mode is "test breaks loudly when the allowlist needs updating" rather than
    "silent privilege expansion."
    """
    if level != 0:
        msg = f"Relative imports are not allowed in generated code: {name!r}"
        raise ImportError(msg)
    top_level = name.split(".", 1)[0]
    if top_level not in _ALLOWED_IMPORT_TOP_LEVELS:
        msg = f"Import of {name!r} is not allowed in generated code"
        raise ImportError(msg)
    return builtins.__import__(name, import_globals, import_locals, fromlist or (), level)


def _make_restricted_builtins() -> dict[str, Any]:
    """Build a builtins dict that blocks dangerous functions and restricts __import__ to an allowlist."""
    safe_builtins = {name: obj for name, obj in vars(builtins).items() if name not in _BLOCKED_BUILTINS}
    safe_builtins["__import__"] = _restricted_import
    return safe_builtins


def _exec_and_extract_class(source_code: str, class_name: str) -> type[BaseModel]:
    """Execute source code and extract the named BaseModel class."""
    namespace: dict[str, Any] = {"__builtins__": _make_restricted_builtins()}
    exec(compile(source_code, "<schema_to_model>", "exec"), namespace)

    # Collect all BaseModel subclasses from the exec'd namespace
    model_classes: dict[str, type[BaseModel]] = {
        name: obj for name, obj in namespace.items() if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel
    }

    # datamodel-code-generator normalizes schema titles to PascalCase class names
    # (e.g. "dynamic_concept_test__Greeting" → "DynamicConceptTestGreeting"),
    # so try both the original name and the normalized version.
    extracted_class = model_classes.get(class_name)
    if extracted_class is None:
        normalized_name = _normalize_class_name(class_name)
        extracted_class = model_classes.get(normalized_name)
    if extracted_class is None:
        available = list(model_classes.keys())
        msg = f"Class '{class_name}' not found in generated source. Available BaseModel classes: {available}"
        raise ValueError(msg)

    # datamodel-code-generator uses `from __future__ import annotations` which turns
    # type annotations into strings. For nested models, we need to rebuild so Pydantic
    # resolves the forward references against all classes in the generated namespace.
    # Include ALL user-defined types (models + enums) so forward references to
    # generated Enum classes (e.g. choices fields) can be resolved.
    all_generated_types: dict[str, Any] = {name: obj for name, obj in namespace.items() if isinstance(obj, type) and not name.startswith("_")}
    for model_cls in model_classes.values():
        model_cls.model_rebuild(_types_namespace=all_generated_types)

    return extracted_class
