from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from mthds.method_tree.lister import list_method_tree
from mthds.method_tree.models import MethodTree
from pytest_mock import MockerFixture

from pipelex.cli.bundle_target_resolution import list_bundle_file_tree, list_method_folder, resolve_method_folder_run
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.libraries.method_tree_listing import MethodTreeListing
from pipelex.pipeline.execution_seams import acquire_library_async
from pipelex.pipeline.fixes.fix_loop import fix_method_folder
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validate_in_process import validate_bundles_in_process

_ECHO_MTHDS = """\
domain = "one_listing"
main_pipe = "echo"

[pipe.echo]
type = "PipeCompose"
description = "Echo the data"
inputs = { data = "Text" }
output = "Text"
template = "$data"
"""


class _ListedPaths:
    """The paths the standard's lister was asked to list a method tree for, as each was handed to it."""

    def __init__(self) -> None:
        self.paths: list[Path] = []

    def under(self, *, directory: Path) -> list[Path]:
        """The paths listed that lie in a directory, the method's own, leaving out the library directories around it."""
        root = directory.resolve()
        return [path for path in self.paths if path.resolve().is_relative_to(root)]


@pytest.fixture(name="listed_paths")
def listed_paths_fixture(mocker: MockerFixture) -> _ListedPaths:
    """Note each path a method tree is listed for, then list it as the standard does."""
    listed = _ListedPaths()

    def list_after_noting_the_path(path: Path, **kwargs: Any) -> MethodTree:
        listed.paths.append(path)
        return list_method_tree(path, **kwargs)

    mocker.patch("pipelex.libraries.method_trees.list_method_tree", side_effect=list_after_noting_the_path)
    return listed


@pytest.fixture(name="method_dir")
def method_dir_fixture(tmp_path: Path) -> Path:
    """A method's folder holding one bundle, whose `main_pipe` is its entry."""
    method_dir = tmp_path / "method"
    method_dir.mkdir()
    (method_dir / "main.mthds").write_text(_ECHO_MTHDS, encoding="utf-8")
    return method_dir


@pytest.fixture(name="outer_library")
def outer_library_fixture() -> Generator[None, None, None]:
    """Tear down the library a test leaves current, and make the library that was current before it current again."""
    outer_library_id = get_current_library_id_or_none()
    yield
    library_id = get_current_library_id_or_none()
    if library_id is not None and library_id != outer_library_id:
        get_library_manager().teardown(library_id=library_id)
    if outer_library_id is not None:
        set_current_library(library_id=outer_library_id)
    else:
        clear_current_library()


@pytest.mark.usefixtures("outer_library")
@pytest.mark.asyncio(loop_scope="class")
class TestOneListingPerRun:
    async def test_a_folder_run_loads_the_tree_its_command_listed_without_listing_it_again(
        self, listed_paths: _ListedPaths, method_dir: Path
    ) -> None:
        """`run bundle <folder>` resolves the folder, then loads it as a library directory and its entry bundle by its file."""
        tree_listing = MethodTreeListing()
        folder_run = resolve_method_folder_run(directory=method_dir, pipe_override=None, tree_listing=tree_listing)
        entry_file = folder_run.entry_bundle_file
        assert entry_file is not None

        library_id, _ = await acquire_library_async(
            "one-listing-folder-run",
            library_dirs=[str(method_dir)],
            mthds_contents=[entry_file.read_text(encoding="utf-8")],
            bundle_uris=[str(entry_file)],
            tree_listing=tree_listing,
        )

        assert listed_paths.under(directory=method_dir) == [method_dir]
        loaded_trees = [
            blueprint.tree_bundle.tree for blueprint in get_library_manager().get_accumulated_blueprints(library_id) if blueprint.tree_bundle
        ]
        assert loaded_trees, "the run loaded no bundle of the method"
        # The tree whose digest the run records is the very tree it loaded.
        assert all(loaded_tree is folder_run.tree for loaded_tree in loaded_trees)

    async def test_a_bundle_file_named_alone_is_placed_in_the_tree_its_command_listed(self, listed_paths: _ListedPaths, method_dir: Path) -> None:
        bundle_file = method_dir / "main.mthds"
        tree_listing = MethodTreeListing()
        method_tree = list_bundle_file_tree(bundle_file=bundle_file, tree_listing=tree_listing)

        library_id, _ = await acquire_library_async(
            "one-listing-file-run",
            mthds_contents=[bundle_file.read_text(encoding="utf-8")],
            bundle_uris=[str(bundle_file)],
            tree_listing=tree_listing,
        )

        assert listed_paths.under(directory=method_dir) == [bundle_file]
        (blueprint,) = get_library_manager().get_accumulated_blueprints(library_id)
        assert blueprint.tree_bundle is not None
        assert blueprint.tree_bundle.tree is method_tree

    async def test_a_load_handed_no_listing_lists_each_tree_once(self, listed_paths: _ListedPaths, method_dir: Path) -> None:
        """A load that is the first to read the method lists it itself, once, for every step of the load."""
        await acquire_library_async(
            "one-listing-own-load",
            library_dirs=[str(method_dir)],
            mthds_contents=[_ECHO_MTHDS],
            bundle_uris=[str(method_dir / "main.mthds")],
        )

        assert listed_paths.under(directory=method_dir) == [method_dir]

    async def test_validating_a_folder_its_command_listed_lists_it_no_more(self, listed_paths: _ListedPaths, method_dir: Path) -> None:
        """`validate bundle <folder>` lists the folder to resolve it, and the validation loads the tree from that listing."""
        tree_listing = MethodTreeListing()
        list_method_folder(directory=method_dir, tree_listing=tree_listing)

        result = await validate_bundle(method_dir=method_dir, library_dirs=[method_dir], library_dirs_are_callers=True, tree_listing=tree_listing)

        assert [pipe.code for pipe in result.pipes] == ["echo"]
        assert listed_paths.under(directory=method_dir) == [method_dir]

    async def test_the_in_process_validator_lists_a_method_once_for_its_load_and_its_graph(
        self, listed_paths: _ListedPaths, method_dir: Path
    ) -> None:
        report = await validate_bundles_in_process(method_dir=method_dir)

        assert report.graph_spec is not None
        assert listed_paths.under(directory=method_dir) == [method_dir]

    async def test_a_fix_of_a_valid_folder_its_command_listed_lists_it_no_more(self, listed_paths: _ListedPaths, method_dir: Path) -> None:
        """The fix loop's snapshot and validation read the listing the command resolved the folder through."""
        tree_listing = MethodTreeListing()
        list_method_folder(directory=method_dir, tree_listing=tree_listing)

        result = await fix_method_folder(method_dir=method_dir, tree_listing=tree_listing)

        assert result.is_valid is True
        assert listed_paths.under(directory=method_dir) == [method_dir]
