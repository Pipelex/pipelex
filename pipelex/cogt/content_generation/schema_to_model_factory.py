"""Reconstruct a Pydantic BaseModel class from a JSON schema using datamodel-code-generator.

This module is the bridge between JSON schema (from model_json_schema()) and a live
BaseModel class that can be used as a structured output schema for LLM generation.
The generated class carries its own source code as __kajson_class_source__, enabling
kajson to deserialize it across process boundaries without a class registry.

Security: this module exec()'s code generated from an attacker-influenceable JSON schema
when schemas cross a process boundary (e.g. Temporal payloads), so two layers of defense
are applied — see SchemaToModelFactory._reject_unsafe_schema_extensions and SchemaToModelFactory._make_restricted_builtins below.
"""

import builtins
import hashlib
import json
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, ClassVar, cast

from pydantic import BaseModel

from pipelex.cogt.content_generation.exceptions import UnsafeSchemaError


class SchemaToModelFactory:
    """Reconstruct Pydantic BaseModel classes from JSON schemas.

    See the module docstring for the threat model and security perimeter.
    """

    _UNSAFE_EXTENSION_PREFIX: ClassVar[str] = "x-python-"

    _BLOCKED_BUILTINS: ClassVar[frozenset[str]] = frozenset({"eval", "exec", "compile", "open", "input", "breakpoint", "exit", "quit"})

    _ALLOWED_IMPORT_TOP_LEVELS: ClassVar[frozenset[str]] = frozenset(
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

    _schema_cache: ClassVar[dict[str, type[BaseModel]]] = {}
    _cache_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def make_from_json_schema(cls, schema: dict[str, Any], class_name: str) -> type[BaseModel]:
        """Reconstruct a BaseModel class from a JSON schema dict.

        Args:
            schema: The JSON schema as returned by SomeModel.model_json_schema().
            class_name: The expected class name (must match the schema's title).

        Returns:
            A BaseModel subclass with __kajson_class_source__ attached.
        """
        cache_key = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()

        # Hold the lock for the entire call. This kills the same-schema thundering herd
        # (N concurrent first-misses each paying a full codegen+exec round) at the cost
        # of also serializing cache hits on other schemas behind any in-flight miss.
        # That trade-off is acceptable because real workloads use a small bounded set
        # of distinct schemas, each generated once and cached for the process lifetime —
        # post-warmup, contention is limited to sub-millisecond cache lookups.
        with cls._cache_lock:
            if cache_key in cls._schema_cache:
                return cls._schema_cache[cache_key]

            source_code = cls._generate_source_from_schema(schema)
            reconstructed_class = cls._exec_and_extract_class(source_code, class_name)
            reconstructed_class.__kajson_class_source__ = source_code  # type: ignore[attr-defined]
            cls._schema_cache[cache_key] = reconstructed_class

        return reconstructed_class

    @classmethod
    def _normalize_class_name(cls, title: str) -> str:
        """Convert a schema title to a PascalCase class name (matching datamodel-code-generator behavior).

        Splits on non-alphanumeric sequences, capitalizes the first char of each segment,
        and preserves existing capitalization within segments (unlike str.title() which
        lowercases everything after the first char).
        """
        segments = re.split(r"[^A-Za-z0-9]+", title)
        return "".join(segment[0].upper() + segment[1:] if segment else "" for segment in segments)

    @classmethod
    def _collect_unsafe_extension_paths(cls, node: Any, path: str, found: list[str]) -> None:
        """Walk a JSON-schema-shaped value, collecting dotted paths to any x-python-* key.

        These extensions cause datamodel-code-generator to emit arbitrary `from X import Y`
        statements with no sanitization, which is a code-injection primitive on any path
        where the schema crosses an untrusted boundary (e.g. Temporal payloads).
        """
        if isinstance(node, dict):
            node_dict = cast("dict[str, Any]", node)
            for key, value in node_dict.items():
                child_path = f"{path}.{key}" if path else key
                if key.startswith(cls._UNSAFE_EXTENSION_PREFIX):
                    found.append(child_path)
                cls._collect_unsafe_extension_paths(value, child_path, found)
        elif isinstance(node, list):
            node_list = cast("list[Any]", node)
            for index, item in enumerate(node_list):
                cls._collect_unsafe_extension_paths(item, f"{path}[{index}]", found)

    @classmethod
    def _reject_unsafe_schema_extensions(cls, schema: dict[str, Any]) -> None:
        """Raise UnsafeSchemaError if the schema contains any x-python-* codegen extension.

        Layer 1 of the SchemaToModelFactory security perimeter: kill the known exploit primitive
        at the source rather than scrubbing it silently — silent stripping would turn a
        malicious payload into a successful run with the attacker's payload merely ignored,
        leaving no signal in logs for incident response.
        """
        found: list[str] = []
        cls._collect_unsafe_extension_paths(schema, "", found)
        if found:
            msg = f"Unsafe codegen extensions found in schema: {found}"
            raise UnsafeSchemaError(msg)

    @classmethod
    def _generate_source_from_schema(cls, schema: dict[str, Any]) -> str:
        """Generate Python source code from a JSON schema using datamodel-code-generator."""
        from datamodel_code_generator import InputFileType, generate  # noqa: PLC0415
        from datamodel_code_generator.enums import DataModelType  # noqa: PLC0415

        cls._reject_unsafe_schema_extensions(schema)

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

    @classmethod
    def _restricted_import(
        cls,
        name: str,
        import_globals: dict[str, Any] | None = None,
        import_locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] | None = (),
        level: int = 0,
    ) -> Any:
        """Replacement for builtin __import__ that allows only an allowlist of modules.

        Layer 2 of the SchemaToModelFactory security perimeter: even if a future codegen feature
        in datamodel-code-generator emits new imports, this wrapper keeps the exec namespace
        constrained to what the generator's output legitimately requires. The intended
        failure mode is "test breaks loudly when the allowlist needs updating" rather than
        "silent privilege expansion."
        """
        if level != 0:
            msg = f"Relative imports are not allowed in generated code: {name!r}"
            raise ImportError(msg)
        top_level = name.split(".", 1)[0]
        if top_level not in cls._ALLOWED_IMPORT_TOP_LEVELS:
            msg = f"Import of {name!r} is not allowed in generated code"
            raise ImportError(msg)
        return builtins.__import__(name, import_globals, import_locals, fromlist or (), level)

    @classmethod
    def _make_restricted_builtins(cls) -> dict[str, Any]:
        """Build a builtins dict that blocks dangerous functions and restricts __import__ to an allowlist."""
        safe_builtins = {name: obj for name, obj in vars(builtins).items() if name not in cls._BLOCKED_BUILTINS}
        safe_builtins["__import__"] = cls._restricted_import
        return safe_builtins

    @classmethod
    def _exec_and_extract_class(cls, source_code: str, class_name: str) -> type[BaseModel]:
        """Execute source code and extract the named BaseModel class."""
        namespace: dict[str, Any] = {"__builtins__": cls._make_restricted_builtins()}
        exec(compile(source_code, "<schema_to_model_factory>", "exec"), namespace)

        # Collect all BaseModel subclasses from the exec'd namespace
        model_classes: dict[str, type[BaseModel]] = {
            name: obj for name, obj in namespace.items() if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel
        }

        # datamodel-code-generator normalizes schema titles to PascalCase class names
        # (e.g. "dynamic_concept_test__Greeting" → "DynamicConceptTestGreeting"),
        # so try both the original name and the normalized version.
        extracted_class = model_classes.get(class_name)
        if extracted_class is None:
            normalized_name = cls._normalize_class_name(class_name)
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
