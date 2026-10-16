import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from mthds.method_tree.digest import digest_of_contents
from mthds.method_tree.lister import list_method_tree

from pipelex.core.method_trees.exceptions import MethodFileUnavailableError
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.exceptions import LibraryError
from pipelex.libraries.pipe_func_call_files import read_pipe_func_call_files
from pipelex.mthds_parsing.parser import MthdsParser

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
    """Sandbox-hosted load: the method's files are NEVER imported in this process, yet the method still loads, its PipeFunc
    validated from its module's source, and its crate names the step's tree by digest, the call reading the tree's files
    through the method file store.
    """

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("sandbox_hosted_mode")
    async def test_hosted_load_names_the_tree_and_its_calls_read_its_files_through_the_store(self):
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

                    # The crate names the step's tree by digest and carries none of its files; a call reads every file
                    # of the tree but its bundles through the method file store, and a file the tree excludes is none.
                    crate = library_manager.get_crate(library_id=library_id)
                    assert crate is not None
                    (tree_digest,) = crate.tree_digests()
                    assert "hello from the sandbox" not in crate.model_dump_json()
                    call_files = await read_pipe_func_call_files(tree_digest=tree_digest, read_scope=None)
                    assert sorted(call_files) == ["hosted_demo_funcs.py", "notes/greeting.txt"]
                    assert call_files["hosted_demo_funcs.py"] == CUSTOMER_FUNC_PY.encode("utf-8")
            finally:
                library_manager.teardown(library_id=library_id)

            # Side-state is cleaned up on teardown: the crate is gone, and the store no longer serves the library's tree.
            assert library_manager.get_crate(library_id=library_id) is None
            with pytest.raises(MethodFileUnavailableError):
                await read_pipe_func_call_files(tree_digest=tree_digest, read_scope=None)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_two_library_directories_submitting_different_files_at_one_path_beside_content_strings_are_refused(self):
        """The files beside content strings make one tree, so two library directories' files at one path must fail loud,
        not silently overwrite one customer's PipeFunc body: the call writes the files at their paths.
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
                with scoped_current_library(library_id=library_id):
                    library_manager.load_libraries(library_id=library_id, library_dirs=[dir_a, dir_b])
                    with pytest.raises(
                        LibraryError, match=re.escape("Two different files were submitted under the same path 'hosted_demo_funcs.py'")
                    ):
                        library_manager.load_from_blueprints(
                            library_id=library_id, blueprints=[MthdsParser.make_pipelex_bundle_blueprint(mthds_content=HOSTED_DEMO_MTHDS)]
                        )
            finally:
                library_manager.teardown(library_id=library_id)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("sandbox_hosted_mode")
    async def test_content_strings_name_the_tree_of_the_files_their_library_directory_submits(self):
        """The directory a server writes a request's files into holds no bundle: its files make the tree the content strings sit at the root of."""
        library_manager = get_library_manager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            library_dir = Path(tmp_dir)
            (library_dir / "hosted_demo_funcs.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")

            library_id, _ = library_manager.open_library()
            try:
                with scoped_current_library(library_id=library_id):
                    library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
                    library_manager.load_from_blueprints(
                        library_id=library_id, blueprints=[MthdsParser.make_pipelex_bundle_blueprint(mthds_content=HOSTED_DEMO_MTHDS)]
                    )
                    crate = library_manager.get_crate(library_id=library_id)
                    assert crate is not None
                    tree_bundle_ref = crate.tree_bundles["hosted_demo.make_note"]
                    assert tree_bundle_ref.tree_path is None
                    assert tree_bundle_ref.tree_digest == digest_of_contents({"hosted_demo_funcs.py": CUSTOMER_FUNC_PY.encode("utf-8")})
                    call_files = await read_pipe_func_call_files(tree_digest=tree_bundle_ref.tree_digest, read_scope=None)
                    assert call_files == {"hosted_demo_funcs.py": CUSTOMER_FUNC_PY.encode("utf-8")}
            finally:
                library_manager.teardown(library_id=library_id)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_two_methods_shipping_different_files_at_one_path_load_side_by_side(self, tmp_path: Path):
        """Each method's calls read its own tree's files, so two methods' README.md, requirements.txt and METHODS.toml never clash."""
        library_manager = get_library_manager()
        _write_method(method_dir=tmp_path / "first", name="first")
        _write_method(method_dir=tmp_path / "second", name="second")

        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                library_manager.load_libraries(library_id=library_id, library_dirs=[tmp_path / "first", tmp_path / "second"])
                crate = library_manager.get_crate(library_id=library_id)
                assert crate is not None
                assert len(crate.tree_digests()) == 2
                assert {tree_bundle_ref.tree_path for tree_bundle_ref in crate.tree_bundles.values()} == {"first.mthds", "second.mthds"}
        finally:
            library_manager.teardown(library_id=library_id)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_the_crate_builds_after_the_directory_its_tree_was_listed_from_is_removed(self, tmp_path: Path):
        """The crate names the tree by its digest alone, so building it reads no file."""
        library_manager = get_library_manager()
        library_dir = tmp_path / "request"
        library_dir.mkdir()
        (library_dir / "make_note.mthds").write_text(HOSTED_DEMO_MTHDS, encoding="utf-8")
        (library_dir / "hosted_demo_funcs.py").write_text(CUSTOMER_FUNC_PY, encoding="utf-8")

        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
                tree_digest = list_method_tree(library_dir).digest
                shutil.rmtree(library_dir)

                crate = library_manager.get_crate(library_id=library_id)

                assert crate is not None
                assert crate.tree_digests() == [tree_digest]
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
