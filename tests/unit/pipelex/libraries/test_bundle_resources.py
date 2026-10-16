import re

import pytest

from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError
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
