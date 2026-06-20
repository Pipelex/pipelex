"""Regression: ``pipelex.system.configuration.config_temporal`` MUST NOT import ``temporalio``
at module level. ``temporalio`` is in ``[project.optional-dependencies].temporal``;
``pipelex.system.configuration.configs`` imports this module unconditionally,
so a top-level temporalio import breaks every install that didn't opt into the
``temporal`` extra.
"""

import ast
from pathlib import Path


def _is_type_checking_guard(test_node: ast.expr) -> bool:
    """Recognize ``if TYPE_CHECKING:`` and ``if typing.TYPE_CHECKING:`` guards.

    Their body is only evaluated by type checkers, never at runtime, so imports
    inside them are safe under the optional-dependency contract.
    """
    if isinstance(test_node, ast.Name) and test_node.id == "TYPE_CHECKING":
        return True
    return isinstance(test_node, ast.Attribute) and test_node.attr == "TYPE_CHECKING"


def _scan_for_runtime_temporalio_imports(nodes: list[ast.stmt], forbidden: list[str]) -> None:
    """Recursively walk module-level statements that execute at import time and
    record any ``temporalio`` import found in them.

    Handles guarded top-level imports the AI bot flagged on PR #880: anything
    inside ``try`` / ``except`` / ``if`` (other than ``if TYPE_CHECKING:``)
    still runs when the module is imported, so it counts as a runtime import.
    Function and class bodies are skipped — their imports only fire when the
    function is called, which is the intended lazy-import pattern.
    """
    for node in nodes:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("temporalio"):
            forbidden.append(f"line {node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("temporalio"):
                    forbidden.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.If):
            # The body of ``if TYPE_CHECKING:`` is invisible to the runtime — skip it.
            # The else branch DOES run at runtime, so scan it regardless.
            if not _is_type_checking_guard(node.test):
                _scan_for_runtime_temporalio_imports(node.body, forbidden)
            _scan_for_runtime_temporalio_imports(node.orelse, forbidden)
        elif isinstance(node, ast.Try):
            _scan_for_runtime_temporalio_imports(node.body, forbidden)
            for handler in node.handlers:
                _scan_for_runtime_temporalio_imports(handler.body, forbidden)
            _scan_for_runtime_temporalio_imports(node.orelse, forbidden)
            _scan_for_runtime_temporalio_imports(node.finalbody, forbidden)
        # ast.FunctionDef / ast.AsyncFunctionDef / ast.ClassDef are intentionally
        # skipped — bodies don't execute at module import time, so a lazy
        # ``from temporalio.common import RetryPolicy`` inside a function body
        # is the intended pattern.


class TestConfigTemporalOptionalDep:
    def test_no_module_level_temporalio_import(self) -> None:
        """No ``import temporalio`` or ``from temporalio... import ...`` reachable
        at module import time (including imports nested in ``try`` / ``except``
        / ``if`` branches other than ``if TYPE_CHECKING:``). ``TYPE_CHECKING``
        blocks and function-local imports are fine.
        """
        source_path = Path(__file__).resolve().parents[4] / "pipelex" / "system" / "configuration" / "config_temporal.py"
        assert source_path.is_file(), f"expected config_temporal.py at {source_path}"
        tree = ast.parse(source_path.read_text())

        forbidden: list[str] = []
        _scan_for_runtime_temporalio_imports(tree.body, forbidden)

        assert not forbidden, (
            "config_temporal.py imports temporalio at module level — "
            "this breaks installs without the 'temporal' extra. "
            f"Move under TYPE_CHECKING or into function bodies. Found: {forbidden}"
        )
