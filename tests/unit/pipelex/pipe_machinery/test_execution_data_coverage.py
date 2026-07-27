"""Every concrete Pipe must call _register_execution_data in both live and dry run.

Prevents regressions where a new pipe is added (or an existing one is refactored)
and forgets to emit execution data. Without this, the graph tracer has no runtime
info for that pipe and the sidepanel shows empty fields.

The check reads the source of each pipe's run entry point and any `self.method(...)`
it calls (transitively), then looks for `self._register_execution_data(`. Static,
fast, no fixture setup.
"""

import importlib
import inspect
import pkgutil
import re

import pytest

from pipelex import pipe_controllers, pipe_operators
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract

REGISTER_CALL = "self._register_execution_data("
SELF_CALL_RE = re.compile(r"self\.(\w+)\(")

LIVE_RUN_METHOD_NAMES = ("_live_run_operator_pipe", "_live_run_controller_pipe")
DRY_RUN_METHOD_NAMES = ("_dry_run_operator_pipe", "_dry_run_controller_pipe")


def _discover_pipe_classes() -> list[type[PipeAbstract]]:
    """Import every pipe module and return concrete leaf PipeAbstract subclasses.

    Excludes signature pipes: a `PipeSignature` is a contract-only placeholder. Its live-run
    raises before any runtime data exists, and its dry-run only mints a mock output — neither
    is a place to register execution data for the graph tracer.
    """
    for package in (pipe_operators, pipe_controllers):
        for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
            importlib.import_module(module_info.name)

    seen: set[type[PipeAbstract]] = set()

    def walk(cls: type[PipeAbstract]) -> None:
        for sub in cls.__subclasses__():
            if sub not in seen:
                seen.add(sub)
                walk(sub)

    walk(PipeAbstract)  # type: ignore[type-abstract]

    leaves = [
        cls
        for cls in seen
        if not cls.__module__.endswith((".pipe_operator", ".pipe_controller", ".pipe_abstract"))
        and not cls.__module__.startswith("pipelex.pipe_signature.")
    ]
    return sorted(leaves, key=lambda c: c.__name__)


def _collect_reachable_source(cls: type[PipeAbstract], method_name: str) -> str:
    """Return the source of `method_name` concatenated with the source of every
    `self.<method>(...)` it calls, transitively. Handles cycles via a visited set.

    This captures the common pattern where an entry point dispatches to helpers:
    e.g. PipeCompose._live_run_operator_pipe → _run_template_mode → _register_execution_data.
    """
    visited: set[str] = set()
    stack: list[str] = [method_name]
    chunks: list[str] = []

    while stack:
        name = stack.pop()
        if name in visited:
            continue
        visited.add(name)

        method = getattr(cls, name, None)
        if method is None:
            continue
        try:
            source = inspect.getsource(method)
        except (OSError, TypeError):
            continue
        chunks.append(source)

        for match in SELF_CALL_RE.finditer(source):
            callee = match.group(1)
            if callee not in visited:
                stack.append(callee)

    return "\n".join(chunks)


_PIPE_CLASSES = _discover_pipe_classes()


class TestPipeExecutionDataCoverage:
    """Every pipe must register execution data in both live and dry run."""

    def test_pipe_classes_were_discovered(self) -> None:
        assert _PIPE_CLASSES, "No Pipe subclasses discovered — check pipe_operators / pipe_controllers imports."

    @pytest.mark.parametrize("pipe_class", _PIPE_CLASSES, ids=lambda c: c.__name__)
    def test_live_run_calls_register_execution_data(self, pipe_class: type[PipeAbstract]) -> None:
        entry = next((name for name in LIVE_RUN_METHOD_NAMES if getattr(pipe_class, name, None) is not None), None)
        assert entry is not None, f"{pipe_class.__name__} must override one of {LIVE_RUN_METHOD_NAMES}"

        source = _collect_reachable_source(pipe_class, entry)
        assert REGISTER_CALL in source, (
            f"{pipe_class.__name__}.{entry} does not call self._register_execution_data(...) "
            f"(directly or via another self-method). Every pipe must register runtime data "
            f"(rendered prompts, resolved models, composed fields, etc.) so the graph sidepanel "
            f"has something to display."
        )

    @pytest.mark.parametrize("pipe_class", _PIPE_CLASSES, ids=lambda c: c.__name__)
    def test_dry_run_calls_register_execution_data(self, pipe_class: type[PipeAbstract]) -> None:
        entry = next((name for name in DRY_RUN_METHOD_NAMES if getattr(pipe_class, name, None) is not None), None)
        assert entry is not None, f"{pipe_class.__name__} must override one of {DRY_RUN_METHOD_NAMES}"

        source = _collect_reachable_source(pipe_class, entry)
        assert REGISTER_CALL in source, (
            f"{pipe_class.__name__}.{entry} does not call self._register_execution_data(...) "
            f"(directly or via another self-method). Dry runs must also register execution data "
            f"for complete dry-run graph visualization."
        )
