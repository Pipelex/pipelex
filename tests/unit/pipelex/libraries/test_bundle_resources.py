import pytest

from pipelex.core.bundle_resources.bundle_resource import BundleResourceReadStage, make_bundle_resources
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError
from pipelex.libraries.bundle_resources import (
    BUNDLE_RESOURCES_STORAGE_PREFIX,
    bundle_resource_reads,
    check_bundle_resources_are_named,
    relocate_run_resources,
)
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

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


class TestBundleResourceReads:
    def test_each_named_file_is_keyed_by_its_canonical_path_with_when_it_is_read(self) -> None:
        """An office template is read when its step runs, an HTML template when the method loads."""
        reads = bundle_resource_reads(pipe_blueprints=(_blueprint().pipe or {}).values())

        assert reads == {"templates/report.docx": BundleResourceReadStage.RUN, "summary.html": BundleResourceReadStage.LOAD}


class TestCheckBundleResourcesAreNamed:
    def test_files_the_steps_name_pass_whatever_their_spelling(self) -> None:
        resources = make_bundle_resources(files={"templates/report.docx": b"docx", "./summary.html": b"<h1></h1>"})

        check_bundle_resources_are_named(blueprints=[_blueprint()], bundle_resources=resources)

    def test_a_file_no_step_names_is_refused_naming_it(self) -> None:
        resources = make_bundle_resources(files={"templates/report.docx": b"docx", "report.docx": b"docx", "logo.png": b"png"})

        with pytest.raises(BundleResourceNotNamedError) as exc_info:
            check_bundle_resources_are_named(blueprints=[_blueprint()], bundle_resources=resources)

        assert "'logo.png', 'report.docx'" in exc_info.value.message
        assert "templates/report.docx" not in exc_info.value.message


@pytest.mark.asyncio
class TestRelocateRunResources:
    async def test_a_file_read_when_its_step_runs_is_stored_and_carried_by_reference(self) -> None:
        """The office template moves to the run's storage; the HTML template, read at load, stays inline."""
        storage_provider = InMemoryStorageProvider()
        resources = make_bundle_resources(files={"templates/report.docx": b"docx bytes", "summary.html": b"<h1></h1>"})
        crate = LibraryCrateFactory.make_from_blueprints([_blueprint()], bundle_resources=resources)

        relocated = await relocate_run_resources(crate=crate, storage_provider=storage_provider, storage_scope="org/method/run")

        stored = relocated.bundle_resources["templates/report.docx"]
        assert stored.uri == f"pipelex-storage://org/method/run/{BUNDLE_RESOURCES_STORAGE_PREFIX}/{stored.sha256}/report.docx"
        assert stored.content_b64 is None
        assert await stored.read_bytes(storage_provider=storage_provider) == b"docx bytes"
        assert relocated.bundle_resources["summary.html"].is_inline
        # The crate the run was built from is left as it was.
        assert crate.bundle_resources["templates/report.docx"].is_inline
        assert relocated.fingerprint == crate.fingerprint

    async def test_a_crate_without_resources_is_returned_as_it_is(self) -> None:
        crate = LibraryCrateFactory.make_from_blueprints([_blueprint()])

        relocated = await relocate_run_resources(crate=crate, storage_provider=InMemoryStorageProvider(), storage_scope="run")

        assert relocated is crate


class TestCrateCarriesResources:
    def test_resources_round_trip_and_stay_out_of_the_fingerprint(self) -> None:
        """Like python_sources, the files travel with the crate but are not part of its structure."""
        resources = make_bundle_resources(files={"templates/report.docx": b"docx bytes"})
        bare = LibraryCrateFactory.make_from_blueprints([_blueprint()])
        with_resources = LibraryCrateFactory.make_from_blueprints([_blueprint()], bundle_resources=resources)

        restored = LibraryCrate.model_validate_json(with_resources.model_dump_json())

        assert restored.bundle_resources == resources
        assert bare.fingerprint == with_resources.fingerprint
