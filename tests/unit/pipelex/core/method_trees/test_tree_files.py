from pathlib import Path

import pytest
from mthds.method_tree.lister import list_method_tree

from pipelex.core.method_trees.exceptions import MethodFileUnavailableError, TreePythonError
from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES
from pipelex.core.method_trees.tree_files import write_call_files
from pipelex.libraries.pipe_func_call_files import read_pipe_func_call_files, travels_with_call

_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00"
_HOLDER = "test_tree_files"


@pytest.fixture
def released_holder():
    yield _HOLDER
    LOCAL_METHOD_FILES.release(holder=_HOLDER)


class TestTreeFiles:
    @pytest.mark.asyncio
    async def test_a_call_receives_every_file_of_the_tree_but_its_bundles_and_what_the_tree_excludes(
        self, tmp_path: Path, released_holder: str
    ) -> None:
        method_dir = tmp_path / "invoicing"
        (method_dir / "funcs").mkdir(parents=True)
        (method_dir / "invoicing.mthds").write_text('domain = "invoicing"\n', encoding="utf-8")
        (method_dir / "funcs" / "totals.py").write_text("TOTAL = 1\n", encoding="utf-8")
        (method_dir / "logo.png").write_bytes(_PNG_BYTES)
        (method_dir / ".gitignore").write_text("scratch.py\n", encoding="utf-8")
        (method_dir / "scratch.py").write_text("NOT_SHIPPED = True\n", encoding="utf-8")
        tree = list_method_tree(method_dir)
        LOCAL_METHOD_FILES.hold_tree(holder=released_holder, tree=tree)

        files = await read_pipe_func_call_files(tree_digest=tree.digest, read_scope=None)

        assert sorted(files) == ["funcs/totals.py", "logo.png"]
        assert files["funcs/totals.py"] == b"TOTAL = 1\n"
        assert files["logo.png"] == _PNG_BYTES

    @pytest.mark.asyncio
    async def test_a_tree_no_library_holds_cannot_be_read(self) -> None:
        with pytest.raises(MethodFileUnavailableError, match="holds no tree"):
            await read_pipe_func_call_files(tree_digest="sha256:" + "0" * 64, read_scope=None)

    def test_a_file_that_is_not_a_generated_structures_module_travels(self) -> None:
        assert travels_with_call(tree_path="logo.png", data=_PNG_BYTES)
        assert travels_with_call(tree_path="helpers.py", data=b"X = 1\n")

    def test_the_files_a_call_received_are_written_at_their_tree_paths(self, tmp_path: Path) -> None:
        write_call_files(files={"funcs/totals.py": b"TOTAL = 1\n", "logo.png": _PNG_BYTES}, destination=tmp_path)

        assert (tmp_path / "funcs" / "totals.py").read_text(encoding="utf-8") == "TOTAL = 1\n"
        assert (tmp_path / "logo.png").read_bytes() == _PNG_BYTES

    @pytest.mark.parametrize("tree_path", ["../escape.py", "/etc/escape.py", "funcs//totals.py"], ids=["climbing", "absolute", "empty-segment"])
    def test_a_key_that_is_not_a_tree_path_is_refused_before_anything_is_written(self, tmp_path: Path, tree_path: str) -> None:
        destination = tmp_path / "call"
        destination.mkdir()

        with pytest.raises(TreePythonError, match="which is not a tree path"):
            write_call_files(files={"first.py": b"X = 1\n", tree_path: b"X = 1\n"}, destination=destination)

        assert not (tmp_path / "escape.py").exists()
        assert not (destination / "first.py").exists()
