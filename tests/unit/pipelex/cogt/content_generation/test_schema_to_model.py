"""Unit tests for schema_to_model: reconstructing BaseModel classes from JSON schemas."""

from typing import Any

import pytest
from pydantic import BaseModel, Field

from pipelex.cogt.content_generation.exceptions import UnsafeSchemaError
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory


class SimpleModel(BaseModel):
    name: str = Field(description="The name")
    age: int = Field(description="The age")


class Address(BaseModel):
    street: str
    city: str


class PersonWithAddress(BaseModel):
    name: str
    address: Address


def _benign_object_schema() -> dict[str, Any]:
    return {"title": "Innocent", "type": "object", "properties": {"x": {"type": "integer"}}}


class TestSchemaToModel:
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
