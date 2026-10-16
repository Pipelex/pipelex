from collections.abc import Generator
from pathlib import Path

import pytest
from mthds.method_tree.digest import digest_of_contents
from mthds.method_tree.models import MethodTree

from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES, write_method_tree
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validate_in_process import validate_bundles_in_process

_GREET_MTHDS = b"""\
domain = "greeting"
main_pipe = "greet"

[pipe.greet]
type = "PipeCompose"
description = "Greet"
inputs = { text = "Text" }
output = "Text"
template = "Hello $text"
"""

_SECOND_GREET_MTHDS = _GREET_MTHDS.replace(b'domain = "greeting"', b'domain = "greeting_too"')

_BROKEN_PYTHON = b"def ok():\n    return 1\n\n\ndef oops(:\n    pass\n"


@pytest.fixture(name="held_tree")
def held_tree_fixture(tmp_path: Path) -> Generator[Path, None, None]:
    """The default tree, written and held as a host holds a request's tree, its directory yielded."""
    contents = {"greet.mthds": _GREET_MTHDS, "notes/readme.txt": b"notes"}
    written = write_method_tree(contents=contents, destination=tmp_path / "tree", expected_digest=digest_of_contents(contents))
    with WRITTEN_METHOD_TREES.holding(tree=written):
        yield tmp_path / "tree"


def _written(*, tmp_path: Path, contents: dict[str, bytes]) -> tuple[MethodTree, Path]:
    """A tree written out as a host writes a request's tree, and the directory it was written as."""
    destination = tmp_path / "tree"
    return write_method_tree(contents=contents, destination=destination, expected_digest=digest_of_contents(contents)), destination


@pytest.mark.asyncio(loop_scope="class")
class TestValidateMethodDir:
    async def test_a_held_tree_validates_whole_its_bundles_named_by_tree_path(self, held_tree: Path) -> None:
        result = await validate_bundle(method_dir=held_tree)

        assert [blueprint.source for blueprint in result.blueprints] == ["greet.mthds"]
        assert [pipe.code for pipe in result.pipes] == ["greet"]

    async def test_every_python_file_of_the_tree_is_read_for_its_syntax(self, tmp_path: Path) -> None:
        """No step names the module, yet the tree's validation refuses it, by tree path and line, before anything loads."""
        tree, method_dir = _written(tmp_path=tmp_path, contents={"greet.mthds": _GREET_MTHDS, "helpers/broken.py": _BROKEN_PYTHON})
        with WRITTEN_METHOD_TREES.holding(tree=tree), pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(method_dir=method_dir)

        (item,) = exc_info.value.pipelex_bundle_blueprint_validation_errors or []
        assert item.source == "helpers/broken.py"
        assert item.line == 5
        assert str(tmp_path) not in exc_info.value.message

    async def test_a_python_file_that_is_not_utf8_is_refused_by_tree_path(self, tmp_path: Path) -> None:
        tree, method_dir = _written(tmp_path=tmp_path, contents={"greet.mthds": _GREET_MTHDS, "helpers/latin.py": b"NAME = '\xe9'\n"})
        with WRITTEN_METHOD_TREES.holding(tree=tree), pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(method_dir=method_dir)

        (item,) = exc_info.value.pipelex_bundle_blueprint_validation_errors or []
        assert item.source == "helpers/latin.py"
        assert "not UTF-8" in item.message

    async def test_the_graph_is_the_trees_entry_pipe(self, held_tree: Path) -> None:
        report = await validate_bundles_in_process(method_dir=held_tree, library_dirs_are_callers=True)

        assert report.graph_spec is not None
        assert report.graph_spec.pipeline_ref.domain == "greeting"
        assert report.graph_spec.pipeline_ref.main_pipe == "greet"

    async def test_a_tree_with_no_entry_pipe_validates_without_a_graph(self, tmp_path: Path) -> None:
        """Two bundles declaring a main_pipe and no manifest leave a run naming no pipe nothing to start at, so nothing is drawn."""
        tree, method_dir = _written(tmp_path=tmp_path, contents={"a.mthds": _GREET_MTHDS, "b.mthds": _SECOND_GREET_MTHDS})
        with WRITTEN_METHOD_TREES.holding(tree=tree):
            report = await validate_bundles_in_process(method_dir=method_dir, library_dirs_are_callers=True)

        assert report.graph_spec is None
