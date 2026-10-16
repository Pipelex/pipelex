from pathlib import Path

import pytest
from mthds.method_tree.digest import digest_of_contents

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.libraries.method_trees import list_library_trees, list_local_method_tree, list_package_method_tree
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES, WrittenMethodTrees, write_method_tree

_CONTENTS: dict[str, bytes] = {
    "main.mthds": b'domain = "written"\n',
    "templates/invoice.html": b"<h1>{{ number }}</h1>",
}


class TestWrittenMethodTrees:
    def test_a_tree_is_written_at_its_tree_paths_and_read_back_as_written(self, tmp_path: Path) -> None:
        contents = dict(_CONTENTS)
        destination = tmp_path / "tree"

        written = write_method_tree(contents=contents, destination=destination, expected_digest=digest_of_contents(contents))

        assert written.digest == digest_of_contents(contents)
        assert written.directory == destination.resolve()
        assert sorted(written.tree_paths) == ["main.mthds", "templates/invoice.html"]
        assert (destination / "templates" / "invoice.html").read_bytes() == contents["templates/invoice.html"]

    def test_a_copy_reading_back_as_another_tree_is_the_hosts_fault(self, tmp_path: Path) -> None:
        contents = {"main.mthds": _CONTENTS["main.mthds"]}

        with pytest.raises(PipelexUnexpectedError, match="reads back as"):
            write_method_tree(contents=contents, destination=tmp_path / "tree", expected_digest=digest_of_contents({"other.mthds": b"x"}))

    def test_a_destination_already_holding_files_is_refused(self, tmp_path: Path) -> None:
        destination = tmp_path / "tree"
        destination.mkdir()
        (destination / "stray.txt").write_text("stray", encoding="utf-8")
        contents = {"main.mthds": _CONTENTS["main.mthds"]}

        with pytest.raises(PipelexUnexpectedError, match="already holds files"):
            write_method_tree(contents=contents, destination=destination, expected_digest=digest_of_contents(contents))

    def test_a_held_tree_is_every_listing_of_its_directory_until_released(self, tmp_path: Path) -> None:
        contents = {"main.mthds": _CONTENTS["main.mthds"]}
        destination = tmp_path / "tree"
        written = write_method_tree(contents=contents, destination=destination, expected_digest=digest_of_contents(contents))
        registry = WrittenMethodTrees()

        with registry.holding(tree=written):
            assert registry.tree_written_at(directory=destination) is written
            assert registry.holds_tree(tree=written) is True

        assert registry.tree_written_at(directory=destination) is None
        assert registry.holds_tree(tree=written) is False

    def test_the_process_registry_answers_every_lister_while_the_tree_is_held(self, tmp_path: Path) -> None:
        contents = {"main.mthds": _CONTENTS["main.mthds"]}
        destination = tmp_path / "tree"
        written = write_method_tree(contents=contents, destination=destination, expected_digest=digest_of_contents(contents))
        # A file written after the tree, which a listing from disk would read, and the held tree does not hold.
        (destination / "late.txt").write_text("late", encoding="utf-8")

        with WRITTEN_METHOD_TREES.holding(tree=written):
            assert list_local_method_tree(handed_over=destination) is written
            assert list_library_trees(library_dir=destination) == [written]
            assert list_package_method_tree(root=destination, package_address="github.com/acme/written") is written

        assert "late.txt" in list_local_method_tree(handed_over=destination).tree_paths

    def test_one_directory_is_held_once(self, tmp_path: Path) -> None:
        contents = {"main.mthds": _CONTENTS["main.mthds"]}
        written = write_method_tree(contents=contents, destination=tmp_path / "tree", expected_digest=digest_of_contents(contents))
        registry = WrittenMethodTrees()

        with registry.holding(tree=written), pytest.raises(PipelexUnexpectedError, match="already held"), registry.holding(tree=written):
            pass
