import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.exceptions import LibraryError
from pipelex.libraries.library_crate import SUBMITTED_PYTHON_ROOT_KEY

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


SIDE_BY_SIDE_MTHDS = """\
domain = "side_by_side_{name}"
description = "One of two methods loaded side by side"

[pipe.make_note]
type = "PipeFunc"
description = "Build a note"
inputs = {{}}
output = "Text"
function_name = "{name}_funcs.make_note_in_sandbox"
"""

SIDE_BY_SIDE_MANIFEST = '[package]\naddress = "github.com/pipelex-tests/{name}-side-by-side"\nversion = "1.0.0"\ndescription = "The {name} method"\n'


def _write_method(*, method_dir: Path, name: str) -> None:
    """A method folder whose README.md, requirements.txt and METHODS.toml say which method it is."""
    method_dir.mkdir(parents=True)
    (method_dir / "METHODS.toml").write_text(SIDE_BY_SIDE_MANIFEST.format(name=name), encoding="utf-8")
    (method_dir / "README.md").write_text(f"# The {name} method\n", encoding="utf-8")
    (method_dir / "requirements.txt").write_text(f"# The {name} method needs nothing beyond Pipelex\n", encoding="utf-8")
    (method_dir / f"{name}.mthds").write_text(SIDE_BY_SIDE_MTHDS.format(name=name), encoding="utf-8")
    (method_dir / f"{name}_funcs.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")


SHADOWING_MTHDS = """\
domain = "shadowing_probe"
description = "A method shipping a module named like a package of the runner"

[pipe.make_note]
type = "PipeFunc"
description = "Build a note"
inputs = {}
output = "Text"
function_name = "shadowing_probe_funcs.make_note_in_sandbox"
"""


def _write_shadowing_method(*, library_dir: Path) -> None:
    """A method shipping a module named like a package this test process imports, which a sandbox need not hold."""
    library_dir.mkdir()
    (library_dir / "shadowing_probe.mthds").write_text(SHADOWING_MTHDS, encoding="utf-8")
    (library_dir / "shadowing_probe_funcs.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")
    (library_dir / "pytest.py").write_text("SHADOW = True\n", encoding="utf-8")


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

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_two_methods_shipping_different_files_at_one_path_load_side_by_side(self, tmp_path: Path):
        """Each method's calls carry its own tree's files, so two methods' README.md, requirements.txt and METHODS.toml never clash."""
        library_manager = get_library_manager()
        _write_method(method_dir=tmp_path / "first", name="first")
        _write_method(method_dir=tmp_path / "second", name="second")

        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                library_manager.load_libraries(library_id=library_id, library_dirs=[tmp_path / "first", tmp_path / "second"])
                crate = library_manager.get_crate(library_id=library_id)
                assert crate is not None
                assert SUBMITTED_PYTHON_ROOT_KEY not in crate.pipe_func_files
                assert len(crate.pipe_func_files) == 2
                readmes = sorted(str(call_files["README.md"]) for call_files in crate.pipe_func_files.values())
                assert readmes == ["# The first method\n", "# The second method\n"]
        finally:
            library_manager.teardown(library_id=library_id)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_the_crate_builds_after_the_directory_its_files_were_read_from_is_removed(self, tmp_path: Path):
        library_manager = get_library_manager()
        library_dir = tmp_path / "request"
        library_dir.mkdir()
        (library_dir / "make_note.mthds").write_text(HOSTED_DEMO_MTHDS, encoding="utf-8")
        (library_dir / "hosted_demo_funcs.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")
        (library_dir / "notes").mkdir()
        (library_dir / "notes" / "greeting.txt").write_text("hello", encoding="utf-8")

        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
                shutil.rmtree(library_dir)

                crate = library_manager.get_crate(library_id=library_id)

                assert crate is not None
                (call_files,) = crate.pipe_func_files.values()
                assert call_files["hosted_demo_funcs.py"] == CUSTOMER_FUNC_PY
                assert call_files["notes/greeting.txt"] == "hello"
        finally:
            library_manager.teardown(library_id=library_id)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_tree_holding_no_pipe_func_step_is_not_carried(self, tmp_path: Path):
        library_manager = get_library_manager()
        library_dir = tmp_path / "no_steps"
        library_dir.mkdir()
        (library_dir / "concepts.mthds").write_text('domain = "no_steps"\n\n[concept]\nMemo = "A memo"\n', encoding="utf-8")
        (library_dir / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")

        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
                crate = library_manager.get_crate(library_id=library_id)
                assert crate is not None
                assert crate.pipe_func_files == {}
        finally:
            library_manager.teardown(library_id=library_id)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_module_named_like_a_runner_package_passes_on_a_sandbox_hosted_deployment(self, tmp_path: Path):
        library_manager = get_library_manager()
        library_dir = tmp_path / "shadowing"
        _write_shadowing_method(library_dir=library_dir)

        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                pipes = library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
                assert any(pipe.code == "make_note" for pipe in pipes)
        finally:
            library_manager.teardown(library_id=library_id)

    def test_a_module_named_like_a_runner_package_is_refused_in_direct_mode(self, tmp_path: Path):
        library_manager = get_library_manager()
        library_dir = tmp_path / "shadowing"
        _write_shadowing_method(library_dir=library_dir)

        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id), pytest.raises(PipeValidationError, match="the module 'pytest'"):
                library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
        finally:
            library_manager.teardown(library_id=library_id)
