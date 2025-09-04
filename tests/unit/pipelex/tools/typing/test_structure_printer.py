# tests/unit/pipelex/tools/typing/test_structure_printer_param.py
from __future__ import annotations

from typing import Any, Set

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.tools.typing.structure_printer import StructurePrinter
from tests.unit.pipelex.tools.typing.data import (
    EXTRACT_MODEL_TYPES_CASES,
    IS_RENDERABLE_TYPE_CASES,
    PRETTY_TYPE_CASES,
    RENDER_MODEL_CASES,
)


class TestStructurePrinter:
    """Parametric tests for StructurePrinter (one test method per public API)."""

    # ---------- pretty_type (single test, many cases) ----------
    @pytest.mark.parametrize("tp, expected", PRETTY_TYPE_CASES)
    def test_pretty_type(self, tp: Any, expected: str):
        assert StructurePrinter().get_type_structure(tp=tp) == expected

    # ---------- extract_model_types (single test, many cases) ----------
    # We assert expected is a SUBSET of found to stay robust if implementation
    # adds additional collected types in the future.
    @pytest.mark.parametrize("tp, expected_types", EXTRACT_MODEL_TYPES_CASES)
    def test_extract_model_types(self, tp: Any, expected_types: Set[Any]):
        found = StructurePrinter().get_type_structure(tp=tp)
        assert expected_types.issubset(found)

    # ---------- is_renderable_type (single test, many cases) ----------
    @pytest.mark.parametrize("typ, expected", IS_RENDERABLE_TYPE_CASES)
    def test_is_renderable_type(self, typ: Any, expected: bool):
        assert StructurePrinter().get_type_structure(tp=typ) is expected

    # ---------- render_model (exact match cases) ----------
    @pytest.mark.parametrize("cls, expected", RENDER_MODEL_CASES)
    def test_render_model_exact(self, cls: Any, expected: str):
        out = StructurePrinter().get_type_structure(tp=cls, base_class=StructuredContent)

        pretty_print(out, title=f"out for {cls}")
        assert out == expected
