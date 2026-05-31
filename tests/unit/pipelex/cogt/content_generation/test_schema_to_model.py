"""Unit tests for SchemaToModelFactory: reconstructing BaseModel classes from JSON schemas."""

import threading
import uuid
from typing import Any, Literal, get_args, get_origin

import pytest
from pydantic import BaseModel, Field
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.exceptions import UnsafeSchemaError
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory


class SimpleModel(BaseModel):
    name: str = Field(description="The name")
    age: int = Field(description="The age")


class ModelWithLiteralChoices(BaseModel):
    """A model whose ``recommendation`` field is a ``Literal`` over string choices.

    Mirrors the shape a `.mthds` ``choices = [...]`` declaration produces: the
    field's JSON schema contains an inline ``enum: [strings]`` array, and the
    Python annotation is ``Literal[...]`` — NOT a named Python enum class.
    """

    recommendation: Literal["Strong Match", "Good Match", "Partial Match", "Poor Match"]


class ModelWithJsonObject(BaseModel):
    """A model with a free-form JSON object field typed ``dict[str, Any]``.

    Mirrors ``JSONContent``, the native content class that a concept refining the
    native ``JSON`` concept resolves to. The ``Any`` in ``dict[str, Any]`` is what
    breaks forward-reference resolution: datamodel-code-generator emits
    ``from __future__ import annotations``, turning the field annotation into the
    string ``"dict[str, Any]"``. If the rebuild namespace does not carry ``Any``,
    ``model_rebuild`` raises ``NameError: name 'Any' is not defined``.
    """

    json_obj: dict[str, Any] = Field(description="The JSON object")


class Address(BaseModel):
    street: str
    city: str


class PersonWithAddress(BaseModel):
    name: str
    address: Address


def _benign_object_schema() -> dict[str, Any]:
    return {"title": "Innocent", "type": "object", "properties": {"x": {"type": "integer"}}}


class TestSchemaToModel:
    def test_literal_choices_field_round_trips_as_literal_not_enum(self) -> None:
        """Round-tripping a ``Literal[str-set]`` field through ``make_from_json_schema``
        must keep it as a ``Literal[...]`` annotation in the reconstructed class.

        Bug repro: today the round-trip silently re-emits the field as a generated
        ``Enum`` class (e.g. ``class Recommendation(Enum)`` with members like
        ``Poor_Match = "Poor Match"``). When this reconstructed class is handed to
        an LLM as the structured-output target, the LLM tends to fill it with the
        Python enum repr (``"Recommendation.Poor_Match"``) instead of the literal
        string (``"Poor Match"``), which then fails Pydantic validation against the
        original choice set.

        We assert two things:
          1. the generated Python source code does NOT introduce an ``Enum`` class
             named after the field (``class Recommendation(Enum)``);
          2. the reconstructed model's ``recommendation`` field annotation is a
             ``Literal[...]`` whose args are exactly the original string choices.
        """
        # Use a unique title so the class-level schema cache never short-circuits
        # this test with a stale (already-correct or already-buggy) result from
        # another test run.
        schema = ModelWithLiteralChoices.model_json_schema()
        unique_title = f"LiteralChoicesRepro_{uuid.uuid4().hex}"
        schema["title"] = unique_title

        result_class = SchemaToModelFactory.make_from_json_schema(schema, unique_title)
        source = getattr(result_class, "__kajson_class_source__", "")

        assert "class Recommendation(Enum)" not in source, (
            "Bug: Literal[...] choices were re-emitted as a generated Enum class. "
            "An LLM targeting this Enum returns 'Recommendation.Poor_Match' (Python "
            "enum repr) instead of the literal 'Poor Match', which fails validation "
            "against the original choice set.\n\nGenerated source:\n" + source
        )

        recommendation_field = result_class.model_fields["recommendation"]
        annotation = recommendation_field.annotation
        assert get_origin(annotation) is Literal, (
            f"Expected the round-tripped 'recommendation' field annotation to be Literal[...], got {annotation!r}. Source:\n{source}"
        )
        assert set(get_args(annotation)) == {
            "Strong Match",
            "Good Match",
            "Partial Match",
            "Poor Match",
        }, f"Literal args drifted during round-trip: {get_args(annotation)!r}"

    def test_json_object_field_reconstructs_without_undefined_any(self) -> None:
        """A schema with a ``dict[str, Any]`` field reconstructs without raising.

        Bug repro: a ``PipeLLM`` whose output is a concept refining the native
        ``JSON`` concept produces a structured-output model carrying an
        ``Any``-typed field (inherited from ``JSONContent``). datamodel-code-generator
        emits ``from __future__ import annotations``, so the field annotation becomes
        the string ``"dict[str, Any]"``. If ``model_rebuild`` runs against a namespace
        that lacks ``Any``, it raises ``PydanticUndefinedAnnotation: name 'Any' is
        not defined``. The rebuild namespace must carry the typing names the generated
        source was written against.
        """
        schema = ModelWithJsonObject.model_json_schema()
        unique_title = f"JsonObjectRepro_{uuid.uuid4().hex}"
        schema["title"] = unique_title

        result_class = SchemaToModelFactory.make_from_json_schema(schema, unique_title)

        source = getattr(result_class, "__kajson_class_source__", "")
        assert "from __future__ import annotations" in source, (
            f"Expected datamodel-code-generator to emit future annotations (so the regression target is meaningful). Source:\n{source}"
        )
        assert "json_obj" in result_class.model_fields
        instance = result_class(json_obj={"category": "vectors", "count": 3})
        assert instance.json_obj == {"category": "vectors", "count": 3}  # type: ignore[attr-defined]

    def test_make_types_from_source_resolves_any_annotation(self) -> None:
        """The receiver path (``make_types_from_source``) rebuilds a model whose
        string annotation references ``Any`` without raising.

        This is the cross-process path: a ``__kajson_class_source__`` payload carrying
        ``from __future__ import annotations`` plus a ``dict[str, Any]`` field must
        rebuild against a namespace that includes ``Any``.
        """
        source = (
            "from __future__ import annotations\n"
            "from typing import Any\n"
            "from pydantic import BaseModel, Field\n"
            "\n\n"
            "class JsonHolder(BaseModel):\n"
            "    json_obj: dict[str, Any] = Field(..., description='The JSON object')\n"
        )

        types = SchemaToModelFactory.make_types_from_source(source)

        json_holder = types["JsonHolder"]
        assert issubclass(json_holder, BaseModel)
        instance = json_holder(json_obj={"k": "v"})
        assert instance.json_obj == {"k": "v"}  # type: ignore[attr-defined]

    def test_simple_model_reconstruction(self) -> None:
        """A simple model can be reconstructed from its JSON schema."""
        schema = SimpleModel.model_json_schema()
        result_class = SchemaToModelFactory.make_from_json_schema(schema, "SimpleModel")

        assert result_class.__name__ == "SimpleModel"
        assert "name" in result_class.model_fields
        assert "age" in result_class.model_fields

    def test_reconstructed_model_can_validate(self) -> None:
        """The reconstructed model can validate data."""
        schema = SimpleModel.model_json_schema()
        result_class = SchemaToModelFactory.make_from_json_schema(schema, "SimpleModel")

        instance = result_class(name="Alice", age=30)
        assert instance.name == "Alice"  # type: ignore[attr-defined]
        assert instance.age == 30  # type: ignore[attr-defined]

    def test_nested_model_reconstruction(self) -> None:
        """A model with nested BaseModel fields (producing $defs) can be reconstructed."""
        schema = PersonWithAddress.model_json_schema()
        result_class = SchemaToModelFactory.make_from_json_schema(schema, "PersonWithAddress")

        instance = result_class(
            name="Bob",
            address={"street": "123 Main", "city": "NYC"},
        )
        assert instance.name == "Bob"  # type: ignore[attr-defined]
        assert instance.address.city == "NYC"  # type: ignore[attr-defined]

    def test_kajson_class_source_attached(self) -> None:
        """The reconstructed class has __kajson_class_source__ with the generated Python source."""
        schema = SimpleModel.model_json_schema()
        result_class = SchemaToModelFactory.make_from_json_schema(schema, "SimpleModel")

        source = getattr(result_class, "__kajson_class_source__", None)
        assert source is not None
        assert "class SimpleModel" in source
        assert "BaseModel" in source

    def test_caching_returns_same_class(self) -> None:
        """Calling with the same schema returns the same class object (cached)."""
        schema = SimpleModel.model_json_schema()
        class_1 = SchemaToModelFactory.make_from_json_schema(schema, "SimpleModel")
        class_2 = SchemaToModelFactory.make_from_json_schema(schema, "SimpleModel")

        assert class_1 is class_2

    def test_different_schemas_different_classes(self) -> None:
        """Different schemas produce different classes even if class names differ."""
        schema_simple = SimpleModel.model_json_schema()
        schema_nested = PersonWithAddress.model_json_schema()

        class_simple = SchemaToModelFactory.make_from_json_schema(schema_simple, "SimpleModel")
        class_nested = SchemaToModelFactory.make_from_json_schema(schema_nested, "PersonWithAddress")

        assert class_simple is not class_nested

    def test_json_roundtrip_with_reconstructed_class(self) -> None:
        """An instance of the reconstructed class survives JSON round-trip."""
        schema = SimpleModel.model_json_schema()
        result_class = SchemaToModelFactory.make_from_json_schema(schema, "SimpleModel")

        instance = result_class(name="Charlie", age=25)
        json_str = instance.model_dump_json()
        restored = result_class.model_validate_json(json_str)
        assert restored.name == "Charlie"  # type: ignore[attr-defined]
        assert restored.age == 25  # type: ignore[attr-defined]

    def test_normalized_class_name_lookup(self) -> None:
        """A class_name with underscores/double-underscores resolves via PascalCase normalization."""
        schema = SimpleModel.model_json_schema()
        # Override the title to simulate a dynamic concept code like "my_namespace__Greeting"
        schema["title"] = "my_namespace__Greeting"
        result_class = SchemaToModelFactory.make_from_json_schema(schema, "my_namespace__Greeting")

        assert "name" in result_class.model_fields
        assert "age" in result_class.model_fields
        instance = result_class(name="Ada", age=40)
        assert instance.name == "Ada"  # type: ignore[attr-defined]

    def test_concurrent_first_miss_generates_source_only_once(self, mocker: MockerFixture) -> None:
        """N threads racing on the same uncached schema must trigger codegen exactly once.

        The cache is class-level state shared across tests, so we use a unique title per
        run to guarantee a cold-cache start. Without serialization, every thread that
        observes the empty cache pays the full _generate_source_from_schema cost.
        """
        schema = SimpleModel.model_json_schema()
        unique_title = f"ConcurrentMiss_{uuid.uuid4().hex}"
        schema["title"] = unique_title

        spy = mocker.spy(SchemaToModelFactory, "_generate_source_from_schema")

        thread_count = 8
        barrier = threading.Barrier(thread_count)
        results: list[type[BaseModel]] = []
        results_lock = threading.Lock()

        def worker() -> None:
            barrier.wait()
            result = SchemaToModelFactory.make_from_json_schema(schema, unique_title)
            with results_lock:
                results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == thread_count
        first_class = results[0]
        for result_class in results[1:]:
            assert result_class is first_class
        assert spy.call_count == 1

    def test_cache_bounded_size_evicts_lru(self, mocker: MockerFixture) -> None:
        """The schema cache caps at _SCHEMA_CACHE_MAX_SIZE and evicts least-recently-used entries.

        Lowers the bound to 3, inserts 4 distinct schemas, and asserts: (1) cache size never
        exceeds the bound, (2) the oldest schema was evicted (re-requesting it triggers
        fresh codegen). Saves and restores the class-level cache to keep the test isolated.
        """
        # Snapshot then clear class-level state so this test is hermetic.
        saved_cache = SchemaToModelFactory._schema_cache.copy()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        SchemaToModelFactory._schema_cache.clear()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        mocker.patch.object(SchemaToModelFactory, "_SCHEMA_CACHE_MAX_SIZE", 3)
        spy = mocker.spy(SchemaToModelFactory, "_generate_source_from_schema")

        try:
            schemas: list[tuple[str, dict[str, Any]]] = []
            for index in range(4):
                schema = SimpleModel.model_json_schema()
                title = f"BoundedCacheTest_{uuid.uuid4().hex}_{index}"
                schema["title"] = title
                schemas.append((title, schema))
                SchemaToModelFactory.make_from_json_schema(schema, title)
                assert len(SchemaToModelFactory._schema_cache) <= 3  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

            assert spy.call_count == 4
            assert len(SchemaToModelFactory._schema_cache) == 3  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

            # Oldest schema (index 0) must have been evicted: re-requesting it triggers fresh codegen.
            oldest_title, oldest_schema = schemas[0]
            SchemaToModelFactory.make_from_json_schema(oldest_schema, oldest_title)
            assert spy.call_count == 5

            # Most-recently-used schema (index 3) must still be cached: no fresh codegen.
            recent_title, recent_schema = schemas[3]
            SchemaToModelFactory.make_from_json_schema(recent_schema, recent_title)
            assert spy.call_count == 5
        finally:
            SchemaToModelFactory._schema_cache.clear()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            SchemaToModelFactory._schema_cache.update(saved_cache)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_exec_blocks_dangerous_builtins(self) -> None:
        """The restricted exec namespace blocks open(), eval(), exec(), and compile()."""
        malicious_source = "from pydantic import BaseModel\nclass Innocent(BaseModel):\n    name: str = 'ok'\nleaked = open('/etc/passwd')\n"
        with pytest.raises(NameError, match="open"):
            SchemaToModelFactory._exec_and_extract_class(malicious_source, "Innocent")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # ---- Layer 1: schema sanitization (x-python-* extensions are rejected) ----

    def test_x_python_import_at_top_level_is_rejected(self) -> None:
        """A schema with x-python-import at the top level is rejected before reaching codegen."""
        schema = _benign_object_schema()
        schema["x-python-import"] = {"module": "subprocess", "name": "run"}
        with pytest.raises(UnsafeSchemaError) as exc_info:
            SchemaToModelFactory.make_from_json_schema(schema, "Innocent")
        assert "x-python-import" in str(exc_info.value)

    def test_x_python_import_in_defs_is_rejected(self) -> None:
        """Realistic exploit shape: x-python-import nested under $defs is rejected.

        This is the actual attack vector — datamodel-code-generator emits
        `from subprocess import run` from this payload with zero sanitization.
        """
        schema: dict[str, Any] = {
            "title": "Innocent",
            "type": "object",
            "properties": {"hit": {"$ref": "#/$defs/Run"}},
            "$defs": {"Run": {"x-python-import": {"module": "subprocess", "name": "run"}}},
        }
        with pytest.raises(UnsafeSchemaError) as exc_info:
            SchemaToModelFactory.make_from_json_schema(schema, "Innocent")
        assert "x-python-import" in str(exc_info.value)

    def test_x_python_type_is_rejected(self) -> None:
        """Sibling extension x-python-type must also be rejected."""
        schema = _benign_object_schema()
        schema["properties"]["x"]["x-python-type"] = "subprocess.Popen"
        with pytest.raises(UnsafeSchemaError) as exc_info:
            SchemaToModelFactory.make_from_json_schema(schema, "Innocent")
        assert "x-python-type" in str(exc_info.value)

    @pytest.mark.parametrize(
        "extension_key",
        [
            "x-python-import",
            "x-python-type",
            "x-python-class-name",
            "x-python-fancy-future-feature",
        ],
    )
    def test_any_x_python_extension_is_rejected(self, extension_key: str) -> None:
        """Future-proofing: any x-python-* extension in the schema is rejected."""
        schema = _benign_object_schema()
        schema[extension_key] = "anything"
        with pytest.raises(UnsafeSchemaError) as exc_info:
            SchemaToModelFactory.make_from_json_schema(schema, "Innocent")
        assert extension_key in str(exc_info.value)

    def test_deeply_nested_x_python_import_is_rejected(self) -> None:
        """The walker must recurse into deeply nested structures (arrays + $defs + properties)."""
        schema: dict[str, Any] = {
            "title": "Outer",
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/Inner"},
                }
            },
            "$defs": {
                "Inner": {
                    "type": "object",
                    "properties": {
                        "evil": {"x-python-import": {"module": "subprocess", "name": "run"}},
                    },
                },
            },
        }
        with pytest.raises(UnsafeSchemaError) as exc_info:
            SchemaToModelFactory.make_from_json_schema(schema, "Outer")
        assert "x-python-import" in str(exc_info.value)

    def test_unsafe_schema_error_names_the_offending_path(self) -> None:
        """The error message points to where the violation was found, for diagnostic logs."""
        schema: dict[str, Any] = {
            "title": "Innocent",
            "type": "object",
            "properties": {"hit": {"$ref": "#/$defs/Run"}},
            "$defs": {"Run": {"x-python-import": {"module": "subprocess", "name": "run"}}},
        }
        with pytest.raises(UnsafeSchemaError) as exc_info:
            SchemaToModelFactory.make_from_json_schema(schema, "Innocent")
        message = str(exc_info.value)
        assert "$defs" in message
        assert "Run" in message

    def test_multiple_violations_are_all_reported(self) -> None:
        """All violations in a single schema are surfaced — incident response needs the full picture."""
        schema: dict[str, Any] = {
            "title": "Innocent",
            "type": "object",
            "properties": {
                "a": {"x-python-import": {"module": "subprocess", "name": "run"}},
                "b": {"x-python-type": "os.system"},
            },
        }
        with pytest.raises(UnsafeSchemaError) as exc_info:
            SchemaToModelFactory.make_from_json_schema(schema, "Innocent")
        message = str(exc_info.value)
        assert "x-python-import" in message
        assert "x-python-type" in message

    # ---- Layer 2: __import__ allowlist (defense-in-depth at the exec boundary) ----

    def test_exec_blocks_import_subprocess(self) -> None:
        """Even bypassing Layer 1, the restricted __import__ blocks `import subprocess`."""
        malicious_source = "from pydantic import BaseModel\nimport subprocess\nclass Innocent(BaseModel):\n    name: str = 'ok'\n"
        with pytest.raises(ImportError, match="subprocess"):
            SchemaToModelFactory._exec_and_extract_class(malicious_source, "Innocent")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_exec_blocks_direct_dunder_import_call(self) -> None:
        """A direct __import__('subprocess') call is also blocked."""
        malicious_source = "from pydantic import BaseModel\nclass Innocent(BaseModel):\n    name: str = 'ok'\n_leak = __import__('subprocess')\n"
        with pytest.raises(ImportError, match="subprocess"):
            SchemaToModelFactory._exec_and_extract_class(malicious_source, "Innocent")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize(
        ("import_line", "expected_module"),
        [
            ("from os import system", "os"),
            ("from socket import socket", "socket"),
            ("import shutil", "shutil"),
            ("from urllib.request import urlopen", "urllib"),
        ],
    )
    def test_exec_blocks_dangerous_imports(self, import_line: str, expected_module: str) -> None:
        """A range of dangerous stdlib imports is blocked by the allowlist."""
        malicious_source = f"from pydantic import BaseModel\n{import_line}\nclass Innocent(BaseModel):\n    name: str = 'ok'\n"
        with pytest.raises(ImportError, match=expected_module):
            SchemaToModelFactory._exec_and_extract_class(malicious_source, "Innocent")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.parametrize(
        "import_line",
        [
            "from pydantic import BaseModel",
            "from typing import Optional",
            "from typing_extensions import override",
            "from datetime import datetime",
            "from decimal import Decimal",
            "from uuid import UUID",
            "from enum import Enum",
            "from __future__ import annotations",
            "from collections.abc import Mapping",
            "import re",
        ],
    )
    def test_exec_allowlisted_imports_succeed(self, import_line: str) -> None:
        """Allowlisted imports required by datamodel-code-generator output continue to work."""
        source = f"{import_line}\nfrom pydantic import BaseModel\nclass Innocent(BaseModel):\n    name: str = 'ok'\n"
        result_class = SchemaToModelFactory._exec_and_extract_class(source, "Innocent")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result_class.__name__ == "Innocent"
