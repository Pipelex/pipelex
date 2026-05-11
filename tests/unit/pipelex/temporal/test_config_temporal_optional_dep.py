"""Regression: ``pipelex.temporal.config_temporal`` MUST NOT import ``temporalio``
at module level. ``temporalio`` is in ``[project.optional-dependencies].temporal``;
``pipelex.system.configuration.configs`` imports this module unconditionally,
so a top-level temporalio import breaks every install that didn't opt into the
``temporal`` extra.
"""

import ast
from pathlib import Path


class TestConfigTemporalOptionalDep:
    def test_no_module_level_temporalio_import(self) -> None:
        """No ``import temporalio`` or ``from temporalio... import ...`` at the
        module top level. ``TYPE_CHECKING`` blocks and function-local imports
        are fine.
        """
        source_path = Path(__file__).resolve().parents[4] / "pipelex" / "temporal" / "config_temporal.py"
        assert source_path.is_file(), f"expected config_temporal.py at {source_path}"
        tree = ast.parse(source_path.read_text())

        forbidden: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("temporalio"):
                forbidden.append(f"line {node.lineno}: from {node.module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("temporalio"):
                        forbidden.append(f"line {node.lineno}: import {alias.name}")

        assert not forbidden, (
            "config_temporal.py imports temporalio at module level — "
            "this breaks installs without the 'temporal' extra. "
            f"Move under TYPE_CHECKING or into function bodies. Found: {forbidden}"
        )
