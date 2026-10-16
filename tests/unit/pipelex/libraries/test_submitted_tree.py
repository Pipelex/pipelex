import re

import pytest
from mthds.method_tree.digest import digest_of_contents

from pipelex.core.bundle_resources.exceptions import BundleResourcePathError
from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES
from pipelex.core.method_trees.tree_bundle import TreeBundleRef
from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint

_COMPOSE_BUNDLE = """
domain = "submitted_tree_tests"

[pipe.greet]
type        = "PipeCompose"
description = "Greet someone"
inputs      = { name = "Text" }
output      = "Text"
template    = "Hello $name"
"""


def _compose_blueprint() -> PipelexBundleBlueprint:
    return MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_COMPOSE_BUNDLE)


class TestSubmittedTree:
    """The files submitted with content strings make one tree, held for the library's runs, that the content strings sit at the root of."""

    def test_the_content_strings_name_the_tree_of_their_submitted_files(self) -> None:
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                library_manager.add_submitted_files(library_id=library_id, submitted_files={"./templates/report.docx": b"docx"})
                library_manager.load_from_blueprints(library_id=library_id, blueprints=[_compose_blueprint()])
                crate = library_manager.get_crate(library_id=library_id)
                assert crate is not None
                tree_bundle_ref = crate.tree_bundles["submitted_tree_tests.greet"]
                assert tree_bundle_ref == TreeBundleRef(tree_digest=digest_of_contents({"templates/report.docx": b"docx"}), tree_path=None)
                assert LOCAL_METHOD_FILES.read_held_file(tree_digest=tree_bundle_ref.tree_digest, tree_path="templates/report.docx") == b"docx"
        finally:
            library_manager.teardown(library_id=library_id)
        assert LOCAL_METHOD_FILES.held_tree(tree_digest=tree_bundle_ref.tree_digest) is None

    @pytest.mark.parametrize(
        "submitted_files",
        [
            pytest.param({"templates/report.docx": b"a", "Templates/report.docx": b"b"}, id="case_folded"),
            pytest.param({"templates": b"a", "templates/report.docx": b"b"}, id="file_and_directory"),
        ],
    )
    def test_files_that_cannot_make_one_tree_are_refused(self, submitted_files: dict[str, bytes]) -> None:
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with pytest.raises(BundleResourcePathError, match="cannot make one tree"):
                library_manager.add_submitted_files(library_id=library_id, submitted_files=submitted_files)
        finally:
            library_manager.teardown(library_id=library_id)

    def test_two_files_submitted_under_one_path_with_different_bytes_are_the_caller_s_conflict(self) -> None:
        """The refusal is the caller's to read, so it is an input error naming the path, and it joins nothing."""
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            library_manager.add_submitted_files(library_id=library_id, submitted_files={"templates/report.docx": b"first"})
            with pytest.raises(BundleResourcePathError, match=re.escape("submitted under the same path 'templates/report.docx'")):
                library_manager.add_submitted_files(library_id=library_id, submitted_files={"notes.txt": b"n", "templates/report.docx": b"second"})
            with scoped_current_library(library_id=library_id):
                library_manager.load_from_blueprints(library_id=library_id, blueprints=[_compose_blueprint()])
                crate = library_manager.get_crate(library_id=library_id)
                assert crate is not None
                assert crate.tree_bundles["submitted_tree_tests.greet"].tree_digest == digest_of_contents({"templates/report.docx": b"first"})
        finally:
            library_manager.teardown(library_id=library_id)
