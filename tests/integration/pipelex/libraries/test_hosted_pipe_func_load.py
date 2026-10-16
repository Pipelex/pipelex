import sys
import tempfile
from pathlib import Path

import pytest

from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.exceptions import LibraryError

HOSTED_DEMO_MTHDS = """\
domain = "hosted_demo"
description = "Hosted PipeFunc demo"

[concept]
Note = "A note produced by customer code"

[pipe.make_note]
type = "PipeFunc"
description = "Build a note via customer-supplied code that runs only in the sandbox"
inputs = {}
output = "Note"
function_name = "hosted_demo_funcs.make_note_in_sandbox"
"""

CUSTOMER_FUNC_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def make_note_in_sandbox(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="hello from the sandbox")
"""


class TestHostedPipeFuncLoad:
    """Sandbox-hosted load: the method's files are captured on the crate and NEVER imported in this process,
    yet the method still loads, its PipeFunc validated from its module's source.
    """

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_hosted_load_captures_the_tree_files_without_importing(self):
        library_manager = get_library_manager()
        # Guard the precondition: the customer module must not already be imported in this process.
        assert "hosted_demo_funcs" not in sys.modules

        with tempfile.TemporaryDirectory() as tmp_dir:
            library_dir = Path(tmp_dir)
            (library_dir / "make_note.mthds").write_text(HOSTED_DEMO_MTHDS, encoding="utf-8")
            (library_dir / "hosted_demo_funcs.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")
            (library_dir / "notes").mkdir()
            (library_dir / "notes" / "greeting.txt").write_text("hello", encoding="utf-8")
            (library_dir / ".gitignore").write_text("scratch.py\n", encoding="utf-8")
            (library_dir / "scratch.py").write_text("NOT_SHIPPED = True\n", encoding="utf-8")

            library_id, _ = library_manager.open_library()
            try:
                with scoped_current_library(library_id=library_id):
                    # Loads cleanly: the PipeFunc's module is located and its form proven from its source.
                    pipes = library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
                    assert any(pipe.code == "make_note" for pipe in pipes)

                    # The customer code was NOT imported in this process.
                    assert "hosted_demo_funcs" not in sys.modules

                    # Every file of the step's tree but its bundles rode along on the crate, ready to travel to a
                    # sandbox; a file the tree excludes did not.
                    crate = library_manager.get_crate(library_id=library_id)
                    assert crate is not None
                    (tree_key,) = {tree_bundle_ref.tree_key for tree_bundle_ref in crate.tree_bundles.values()}
                    assert sorted(crate.pipe_func_files[tree_key]) == ["hosted_demo_funcs.py", "notes/greeting.txt"]
                    assert crate.pipe_func_files[tree_key]["hosted_demo_funcs.py"] == CUSTOMER_FUNC_PY
                    # Carrying files leaves the structural fingerprint untouched.
                    assert crate.fingerprint == crate.compute_fingerprint()
            finally:
                library_manager.teardown(library_id=library_id)

            # Side-state is cleaned up on teardown: a fresh crate for the same id is gone.
            assert library_manager.get_crate(library_id=library_id) is None

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_hosted_load_rejects_colliding_source_paths(self):
        """Two library dirs sharing a file path (with different content) must fail loud, not
        silently overwrite one customer's PipeFunc body — the sandbox writes the files at their paths.
        """
        library_manager = get_library_manager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_a = Path(tmp_dir) / "a"
            dir_b = Path(tmp_dir) / "b"
            dir_a.mkdir()
            dir_b.mkdir()
            # Same relative path in both dirs, different content -> a genuine conflict.
            (dir_a / "hosted_demo_funcs.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")
            (dir_b / "hosted_demo_funcs.py").write_text(CUSTOMER_FUNC_PY.replace("hello from the sandbox", "a different body"), encoding="utf-8")

            library_id, _ = library_manager.open_library()
            try:
                with scoped_current_library(library_id=library_id), pytest.raises(LibraryError, match="Duplicate PipeFunc file path"):
                    library_manager.load_libraries(library_id=library_id, library_dirs=[dir_a, dir_b])
            finally:
                library_manager.teardown(library_id=library_id)
