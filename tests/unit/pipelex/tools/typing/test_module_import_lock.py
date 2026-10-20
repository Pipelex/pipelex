import sys
import threading
import time
import types
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from pipelex.tools.typing.module_inspector import convert_file_path_to_module_path, drop_module_dirs_inserted_under, import_module_from_file

#: How long a test waits for a thread to reach a point it signals, which bounds a regression's run.
_SIGNAL_TIMEOUT_SECONDS = 10.0
#: How long a test lets a second import run before it checks that it is still waiting.
_SETTLE_SECONDS = 0.1
#: The `sys.modules` key of the module through which a test hands the module it imports the events that pace its execution.
_SIGNALS_MODULE = "_pipelex_test_module_import_lock_signals"

_SLOW_MODULE = f"""\
import sys

_signals = sys.modules[{_SIGNALS_MODULE!r}]
_signals.started.set()
if not _signals.release.wait(timeout={_SIGNAL_TIMEOUT_SECONDS}):
    raise AssertionError("the slow module was never released")


class LateClass:
    pass
"""

_FAILING_MODULE = """\
class EarlyClass:
    pass


raise RuntimeError("the module fails while it executes")
"""


@pytest.fixture(name="module_dir")
def module_dir_fixture(tmp_path: Path) -> Generator[Path, None, None]:
    """A directory for the modules a test imports by file, whose modules and `sys.path` entries are dropped after it."""
    signals = types.ModuleType(_SIGNALS_MODULE)
    vars(signals).update(started=threading.Event(), release=threading.Event())
    sys.modules[_SIGNALS_MODULE] = signals
    try:
        yield tmp_path
    finally:
        signals.release.set()
        sys.modules.pop(_SIGNALS_MODULE, None)
        for python_file in tmp_path.glob("*.py"):
            sys.modules.pop(convert_file_path_to_module_path(python_file), None)
        drop_module_dirs_inserted_under(directory=tmp_path.resolve())


def _signals() -> Any:
    return sys.modules[_SIGNALS_MODULE]


class TestModuleImportLock:
    def test_two_concurrent_imports_of_one_file_both_get_the_complete_module(self, module_dir: Path) -> None:
        """The module is published before it executes: the second import waits for the execution, never takes it half done."""
        module_file = module_dir / "slow_structures.py"
        module_file.write_text(_SLOW_MODULE, encoding="utf-8")
        signals = _signals()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(import_module_from_file, module_file)
            assert signals.started.wait(timeout=_SIGNAL_TIMEOUT_SECONDS), "the first import never executed the module"
            second = executor.submit(import_module_from_file, module_file)
            time.sleep(_SETTLE_SECONDS)
            assert not second.done(), "the second import returned while the module was still executing"
            signals.release.set()
            first_module = first.result(timeout=_SIGNAL_TIMEOUT_SECONDS)
            second_module = second.result(timeout=_SIGNAL_TIMEOUT_SECONDS)

        assert first_module is second_module
        assert hasattr(first_module, "LateClass")

    def test_a_module_failing_to_execute_leaves_sys_modules(self, module_dir: Path) -> None:
        """As with the import system's own imports, a later import executes it again rather than take it half executed."""
        module_file = module_dir / "failing_structures.py"
        module_file.write_text(_FAILING_MODULE, encoding="utf-8")

        with pytest.raises(RuntimeError, match="the module fails while it executes"):
            import_module_from_file(module_file)

        assert convert_file_path_to_module_path(module_file) not in sys.modules
