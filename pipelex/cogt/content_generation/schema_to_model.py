"""Reconstruct a Pydantic BaseModel class from a JSON schema using datamodel-code-generator.

This module is the bridge between JSON schema (from model_json_schema()) and a live
BaseModel class that can be used as a structured output schema for LLM generation.
The generated class carries its own source code as __kajson_class_source__, enabling
kajson to deserialize it across process boundaries without a class registry.
"""

import hashlib
import json
import tempfile
import threading
from pathlib import Path
from typing import Any

from datamodel_code_generator.parser.base import title_to_class_name
from pydantic import BaseModel

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
        _schema_cache[cache_key] = reconstructed_class

    return reconstructed_class


def _generate_source_from_schema(schema: dict[str, Any]) -> str:
    """Generate Python source code from a JSON schema using datamodel-code-generator."""
    from datamodel_code_generator import InputFileType, generate  # noqa: PLC0415
    from datamodel_code_generator.enums import DataModelType  # noqa: PLC0415

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


def _exec_and_extract_class(source_code: str, class_name: str) -> type[BaseModel]:
    """Execute source code and extract the named BaseModel class."""
    namespace: dict[str, Any] = {}
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
        normalized_name = title_to_class_name(class_name)
        extracted_class = model_classes.get(normalized_name)
    if extracted_class is None:
        available = list(model_classes.keys())
        msg = f"Class '{class_name}' not found in generated source. Available BaseModel classes: {available}"
        raise ValueError(msg)

    # datamodel-code-generator uses `from __future__ import annotations` which turns
    # type annotations into strings. For nested models, we need to rebuild so Pydantic
    # resolves the forward references against all classes in the generated namespace.
    for model_cls in model_classes.values():
        model_cls.model_rebuild(_types_namespace=model_classes)

    return extracted_class
