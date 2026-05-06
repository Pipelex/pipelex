"""Reconstruct a Pydantic BaseModel class from a JSON schema using datamodel-code-generator.

This module is the bridge between JSON schema (from model_json_schema()) and a live
BaseModel class that can be used as a structured output schema for LLM generation.
The generated class carries its own source code as __kajson_class_source__, enabling
kajson to deserialize it across process boundaries without a class registry.

Security model: this module exec()'s code generated from an attacker-influenceable JSON
schema when schemas cross a process boundary (e.g. Temporal payloads). Two layers
narrow the attack surface, but Layer 2 is defense-in-depth, NOT a sandbox:

- Layer 1 — `_reject_unsafe_schema_extensions`: rejects `x-python-*` codegen extensions,
  the only currently-known primitive that lets a JSON schema influence emitted imports.
  This is the real defense.
- Layer 2 — `_make_restricted_builtins`: removes a small allowlist of dangerous builtins
  (eval/exec/compile/open/...) and restricts `__import__` to a fixed top-level allowlist.
  This narrows the surface but does NOT contain a determined attacker: `__build_class__`,
  `getattr`, `type`, and `object` remain reachable, so `().__class__.__base__.__subclasses__()`
  can enumerate all loaded classes from inside the exec'd namespace. Any future codegen
  vector that emits arbitrary Python (beyond the schema-driven `from X import Y`
  statements we already block) would let an attacker pivot via that enumeration.

Operationally: if Pipelex's threat model ever shifts to fully untrusted schemas (e.g.
multi-tenant where one tenant can submit arbitrary schemas that another tenant's worker
will codegen), replace exec() with a real sandbox (subprocess + seccomp) or migrate to
programmatic class construction via `pydantic.create_model()` — see the TODO inside
`_exec_and_extract_class`.
"""

import builtins
import hashlib
import json
import re
import tempfile
import threading
from collections import OrderedDict
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

from pydantic import BaseModel, RootModel

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

    _SCHEMA_CACHE_MAX_SIZE: ClassVar[int] = 1024

    _schema_cache: ClassVar[OrderedDict[str, type[BaseModel]]] = OrderedDict()
    _cache_lock: ClassVar[threading.Lock] = threading.Lock()

    _SOURCE_CACHE_MAX_SIZE: ClassVar[int] = 1024

    _source_cache: ClassVar[OrderedDict[str, dict[str, type[Any]]]] = OrderedDict()
    _source_cache_lock: ClassVar[threading.Lock] = threading.Lock()

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
                cls._schema_cache.move_to_end(cache_key)
                return cls._schema_cache[cache_key]

            source_code = cls._generate_source_from_schema(schema)
            reconstructed_class = cls._exec_and_extract_class(source_code, class_name)
            reconstructed_class.__kajson_class_source__ = source_code  # type: ignore[attr-defined]
            if len(cls._schema_cache) >= cls._SCHEMA_CACHE_MAX_SIZE:
                cls._schema_cache.popitem(last=False)
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
        from datamodel_code_generator import InputFileType, LiteralType, generate  # noqa: PLC0415
        from datamodel_code_generator.enums import DataModelType  # noqa: PLC0415

        cls._reject_unsafe_schema_extensions(schema)

        schema_str = json.dumps(schema)

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
            output_path = Path(tmp.name)

        try:
            # We pass formatters=[] (skip formatting entirely) for two reasons:
            # 1. The output is exec()'d and also shipped verbatim as __kajson_class_source__
            #    across Temporal payloads, so cosmetic formatting has no functional value.
            # 2. The default formatters (black + isort) emit a FutureWarning that they'll
            #    be replaced by ruff, but ruff isn't a runtime dep of pipelex or of
            #    datamodel-code-generator's core install. An empty list silences the
            #    warning without forcing a new runtime dependency on consumers.
            # `enum_field_as_literal=LiteralType.All` keeps `enum: [strings]` schema
            # nodes as Python `Literal[...]` annotations instead of regenerating a
            # named `Enum` class. Without it, a `Literal[...]` field round-trips into
            # a plain `Enum` (e.g. `class Recommendation(Enum): Poor_Match = "Poor Match"`),
            # and an LLM filling that schema returns the Python repr
            # `"Recommendation.Poor_Match"` instead of the value `"Poor Match"`,
            # which then fails Pydantic validation against the original choice set.
            generate(
                input_=schema_str,
                input_file_type=InputFileType.JsonSchema,
                output=output_path,
                output_model_type=DataModelType.PydanticV2BaseModel,
                enum_field_as_literal=LiteralType.All,
                formatters=[],
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
        """Build a builtins dict that blocks dangerous functions and restricts __import__ to an allowlist.

        This is defense-in-depth, not a sandbox. `__build_class__`, `getattr`, `type`,
        and `object` remain reachable, so `().__class__.__base__.__subclasses__()` can
        enumerate all loaded classes from inside the exec'd namespace. The real defense
        is `_reject_unsafe_schema_extensions` (Layer 1), which prevents the codegen
        from emitting attacker-controlled imports in the first place.
        """
        safe_builtins = {name: obj for name, obj in vars(builtins).items() if name not in cls._BLOCKED_BUILTINS}
        safe_builtins["__import__"] = cls._restricted_import
        return safe_builtins

    @classmethod
    def _exec_source_to_types(cls, source_code: str) -> dict[str, type[Any]]:
        """Exec source through restricted builtins, return all top-level BaseModel + Enum
        subclasses with model_rebuild applied so forward references resolve.

        Internal primitive shared by both make_types_from_source (receiver path) and
        _exec_and_extract_class (sender path).
        """
        # TODO: replace exec() with programmatic construction via pydantic.create_model().
        # Eliminates the exec primitive entirely, removes the need for both security
        # layers, and lets us delete _make_restricted_builtins/_restricted_import.
        # Non-trivial because nested models, enums, and forward references currently
        # rely on datamodel-code-generator's output structure.
        namespace: dict[str, Any] = {"__builtins__": cls._make_restricted_builtins()}
        exec(compile(source_code, "<schema_to_model_factory>", "exec"), namespace)

        all_user_types: dict[str, type[Any]] = {
            name: obj
            for name, obj in namespace.items()
            if isinstance(obj, type)
            and not name.startswith("_")
            and (issubclass(obj, BaseModel) or issubclass(obj, Enum))
            and obj is not BaseModel
            and obj is not RootModel
            and obj is not Enum
        }

        # datamodel-code-generator uses `from __future__ import annotations` which turns
        # type annotations into strings. Rebuild every BaseModel so forward refs (including
        # references to generated Enum classes for choices fields, and Literal annotations
        # produced by `enum_field_as_literal=All`) resolve against the full type namespace.
        rebuild_namespace: dict[str, Any] = {**all_user_types, "Literal": Literal}
        for candidate in all_user_types.values():
            if issubclass(candidate, BaseModel):
                candidate.model_rebuild(_types_namespace=rebuild_namespace)

        return all_user_types

    @classmethod
    def make_types_from_source(cls, source_code: str) -> dict[str, type[Any]]:
        """Receiver-side entry: exec generated source and return all top-level user-defined
        types (BaseModel + Enum subclasses) keyed by class name.

        Cached by sha256(source_code) so repeated payloads carrying the same dynamic
        class don't re-exec. Returns a shallow copy so callers can mutate freely.

        Security note: this path takes pre-generated Python source (typically delivered
        via `__kajson_class_source__` on a Temporal payload) and exec()'s it directly.
        Layer 1 (`_reject_unsafe_schema_extensions`) does NOT apply here — only Layer 2
        (`_make_restricted_builtins`) does, so the attack surface is materially wider
        than the sender path in `make_from_json_schema`. An attacker who can inject a
        crafted `__kajson_class_source__` string into a cross-process payload bypasses
        the JSON-schema extension check entirely. The TODO in `_exec_source_to_types`
        to migrate to `pydantic.create_model()` would close this gap by removing the
        exec primitive on both paths.
        """
        cache_key = hashlib.sha256(source_code.encode()).hexdigest()
        with cls._source_cache_lock:
            if cache_key in cls._source_cache:
                cls._source_cache.move_to_end(cache_key)
                return dict(cls._source_cache[cache_key])

            types_dict = cls._exec_source_to_types(source_code)
            if len(cls._source_cache) >= cls._SOURCE_CACHE_MAX_SIZE:
                cls._source_cache.popitem(last=False)
            cls._source_cache[cache_key] = types_dict
            return dict(types_dict)

    @classmethod
    def _exec_and_extract_class(cls, source_code: str, class_name: str) -> type[BaseModel]:
        """Execute source code and extract the named BaseModel class."""
        all_user_types = cls.make_types_from_source(source_code)
        model_classes: dict[str, type[BaseModel]] = {name: obj for name, obj in all_user_types.items() if issubclass(obj, BaseModel)}

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

        return extracted_class
