from pathlib import Path

from pytest_mock import MockerFixture

from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES
from pipelex.interpreter_hub import get_library_manager, scoped_current_library

_MANIFEST = '[package]\naddress = "github.com/pipelex-tests/tree-holds"\nversion = "1.0.0"\ndescription = "A method of several bundles"\n'


def _bundle(*, domain: str) -> str:
    return f"""
domain = "{domain}"

[pipe.greet]
type        = "PipeCompose"
description = "Greet someone"
inputs      = {{ name = "Text" }}
output      = "Text"
template    = "Hello $name"
"""


class TestLibraryTreeHolds:
    def test_a_tree_of_several_bundles_is_held_once_and_released_with_its_library(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Holding a tree indexes every file it lists, so a load holds each tree once, not once per bundle it places there."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        (method_dir / "METHODS.toml").write_text(_MANIFEST, encoding="utf-8")
        for domain in ("tree_holds_first", "tree_holds_second", "tree_holds_third"):
            (method_dir / f"{domain}.mthds").write_text(_bundle(domain=domain), encoding="utf-8")
        hold_tree_spy = mocker.spy(LOCAL_METHOD_FILES, "hold_tree")
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                library_manager.load_libraries(library_id=library_id, library_dirs=[method_dir])
            hold_tree_spy.assert_called_once()
            tree = hold_tree_spy.call_args.kwargs["tree"]
            assert LOCAL_METHOD_FILES.holds(holder=library_id, tree_digest=tree.digest)
        finally:
            library_manager.teardown(library_id=library_id)
        assert not LOCAL_METHOD_FILES.holds(holder=library_id, tree_digest=tree.digest)
