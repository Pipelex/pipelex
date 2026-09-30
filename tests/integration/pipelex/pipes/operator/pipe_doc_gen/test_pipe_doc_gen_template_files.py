from pathlib import Path

import pytest

from pipelex.cogt.doc_gen.template_check import TemplateFinding, TemplateFindingSeverity
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines, write_bundle

_DOCX_TEMPLATE_STEP = 'format = "docx"\ntemplate_file = "invoice.docx"'


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenTemplateFiles:
    @pytest.mark.usefixtures("stub_engines")
    @pytest.mark.parametrize(
        ("template_file", "expected"),
        [
            ("invoice.docx", "does not exist"),
            ("../outside.docx", "outside its bundle's directory"),
        ],
        ids=["missing_file", "outside_the_bundle"],
    )
    async def test_a_template_file_is_found_inside_the_bundle_s_directory(self, tmp_path: Path, template_file: str, expected: str) -> None:
        """A template file must exist beside the bundle, and a path out of the bundle's directory is refused even when the file exists."""
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        (tmp_path / "outside.docx").write_bytes(b"docx")
        bundle_path = write_bundle(directory=bundle_dir, step_fields=f'format = "docx"\ntemplate_file = "{template_file}"')

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        assert expected in str(exc_info.value.to_error_report().model_dump())

    async def test_the_engine_s_checker_findings_fail_the_dry_run(self, tmp_path: Path, stub_engines: StubEngines) -> None:
        """The dry run hands the checker the file's bytes, the inputs' shapes and the mock data, and an error finding fails it."""
        (tmp_path / "invoice.docx").write_bytes(b"docx bytes")
        bundle_path = write_bundle(directory=tmp_path, step_fields=_DOCX_TEMPLATE_STEP)
        stub_engines.findings = [TemplateFinding(severity=TemplateFindingSeverity.ERROR, message="The tag {{ invoice.totl }} names no field")]

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        assert "invoice.totl" in str(exc_info.value.to_error_report().model_dump())
        (request,) = stub_engines.check_requests
        assert request.template == b"docx bytes"
        assert request.template_name == "invoice.docx"
        assert set(request.inputs["invoice"].fields) == {"number", "customer", "notes", "line_items"}
        assert request.data is not None
        assert set(request.data) == {"invoice"}

    async def test_warnings_alone_pass_and_print_nothing(self, tmp_path: Path, stub_engines: StubEngines) -> None:
        """A warning is logged, not raised, and the dry run prints nothing."""
        (tmp_path / "invoice.docx").write_bytes(b"docx bytes")
        bundle_path = write_bundle(directory=tmp_path, step_fields=_DOCX_TEMPLATE_STEP)
        stub_engines.findings = [TemplateFinding(severity=TemplateFindingSeverity.WARNING, message="The notes are never printed")]

        await validate_bundle(mthds_file_path=bundle_path)

        assert len(stub_engines.check_requests) == 1
        assert stub_engines.engine.jobs == []
