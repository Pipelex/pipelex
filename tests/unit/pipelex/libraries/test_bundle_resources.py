import re

import pytest
from mthds.method_tree.digest import digest_of_contents

from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError, BundleResourcePathError
from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES
from pipelex.core.method_trees.tree_bundle import TreeBundleRef
from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.bundle_resources import check_submitted_files, named_bundle_files
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint

_BUNDLE = """
domain = "bundle_resources_tests"
main_pipe = "print_report"

[concept.Report]
description = "A report"

[concept.ReportFile]
description = "The report as a file"
refines     = "Document"

[pipe.print_report]
type          = "PipeDocGen"
description   = "Print the report in Word"
inputs        = { report = "Report" }
output        = "ReportFile"
format        = "docx"
template_file = "./templates/report.docx"

[pipe.print_summary]
type          = "PipeDocGen"
description   = "Print the summary as a PDF"
inputs        = { report = "Report" }
output        = "ReportFile"
format        = "pdf"
template_file = "summary.html"
"""


def _blueprint() -> PipelexBundleBlueprint:
    return MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_BUNDLE)


class TestSubmittedFiles:
    def test_each_named_file_is_keyed_by_its_canonical_path(self) -> None:
        named = named_bundle_files(pipe_blueprints=(_blueprint().pipe or {}).values())

        assert named == {"templates/report.docx", "summary.html"}

    def test_files_the_steps_name_pass_whatever_their_spelling(self) -> None:
        check_submitted_files(blueprints=[_blueprint()], submitted_files={"templates//report.docx": b"docx", "./summary.html": b"<h1></h1>"})

    def test_a_file_no_step_names_is_refused_naming_it(self) -> None:
        with pytest.raises(BundleResourceNotNamedError, match=re.escape("'templates/other.docx'")):
            check_submitted_files(blueprints=[_blueprint()], submitted_files={"templates/other.docx": b"docx"})

    def test_no_file_submitted_is_no_refusal(self) -> None:
        check_submitted_files(blueprints=[_blueprint()], submitted_files={})

    def test_a_bundle_in_no_tree_names_none_in_its_crate(self) -> None:
        """A bundle parsed from a string with no file submitted beside it belongs to no tree."""
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[_blueprint()])

        assert crate.tree_bundles == {}
        assert crate.tree_digests() == []


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
