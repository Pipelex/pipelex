import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from pipelex.config import get_config
from pipelex.libraries.exceptions import LibraryError
from pipelex.method_hub import get_library_manager, scoped_current_library
from pipelex.system.registries.func_registry import func_registry

HOSTED_DEMO_MTHDS = """\
domain = "hosted_demo"
description = "Hosted PipeFunc demo"

[concept]
Note = "A note produced by customer code"

[pipe.make_note]
type = "PipeFunc"
description = "Build a note via customer-supplied code that lives only in the sandbox"
inputs = {}
output = "Note"
function_name = "make_note_in_sandbox"
"""

CUSTOMER_FUNC_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func(name="make_note_in_sandbox")
async def make_note_in_sandbox(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="hello from the sandbox")
"""


@pytest.fixture
def sandbox_hosted_mode() -> Generator[None, None, None]:
    """Select a non-``direct`` execution mode for the duration of a test, then restore it.

    Flipping config (not monkeypatching the helper) exercises the genuine
    is_pipe_func_sandbox_hosted() read at every call site (loader + validators) together: any
    non-``direct`` mode is sandbox-hosted. The concrete sandbox modes live in the out-of-tree closed
    plugin, so this open-core test uses a neutral ``"sandbox"`` token — it only flips the hosted flag
    (the executor already on the hub is never re-resolved here), so no registered mode is needed.
    """
    pipe_func_config = get_config().pipelex.pipe_func_config
    previous = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "sandbox"
    try:
        yield
    finally:
        pipe_func_config.execution_mode = previous


class TestHostedPipeFuncLoad:
    """Sandbox-hosted load: the customer's PipeFunc .py is captured as crate source and is NEVER
    registered/executed in this process, yet the method still loads (validators skip the callable).
    """

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_hosted_load_captures_source_without_registering(self):
        library_manager = get_library_manager()
        function_name = "make_note_in_sandbox"
        # Guard the precondition: the customer function must not already be in the process registry.
        assert func_registry.get_function(function_name) is None

        with tempfile.TemporaryDirectory() as tmp_dir:
            library_dir = Path(tmp_dir)
            (library_dir / "make_note.mthds").write_text(HOSTED_DEMO_MTHDS, encoding="utf-8")
            (library_dir / "customer_func.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")

            library_id, _ = library_manager.open_library()
            try:
                with scoped_current_library(library_id=library_id):
                    # Loads cleanly even though the function is absent here: hosted-mode validators skip
                    # the func_registry lookup and the return-type check.
                    pipes = library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
                    assert any(pipe.code == "make_note" for pipe in pipes)

                    # The customer code was NOT imported/registered in this process.
                    assert func_registry.get_function(function_name) is None

                    # The .py source rode along on the crate, ready to travel to a sandbox.
                    crate = library_manager.get_crate(library_id=library_id)
                    assert crate is not None
                    assert crate.python_sources.get("customer_func.py") == CUSTOMER_FUNC_PY
                    # Carrying source leaves the structural fingerprint untouched.
                    assert crate.fingerprint == crate.compute_fingerprint()
            finally:
                library_manager.teardown(library_id=library_id)

            # Side-state is cleaned up on teardown: a fresh crate for the same id is gone.
            assert library_manager.get_crate(library_id=library_id) is None

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_hosted_load_rejects_colliding_source_paths(self):
        """Two library dirs sharing a source relpath (with different content) must fail loud, not
        silently overwrite one customer's PipeFunc body — the sandbox writes sources flat by relpath.
        """
        library_manager = get_library_manager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_a = Path(tmp_dir) / "a"
            dir_b = Path(tmp_dir) / "b"
            dir_a.mkdir()
            dir_b.mkdir()
            # Same relative path in both dirs, different content -> a genuine conflict.
            (dir_a / "customer_func.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")
            (dir_b / "customer_func.py").write_text(CUSTOMER_FUNC_PY.replace("hello from the sandbox", "a different body"), encoding="utf-8")

            library_id, _ = library_manager.open_library()
            try:
                with scoped_current_library(library_id=library_id), pytest.raises(LibraryError, match="Duplicate PipeFunc source path"):
                    library_manager.load_libraries(library_id=library_id, library_dirs=[dir_a, dir_b])
            finally:
                library_manager.teardown(library_id=library_id)
