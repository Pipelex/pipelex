from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.cogt.doc_gen.input_shape import InputShapeKind
from pipelex.cogt.doc_gen.template_check import TemplateFinding, TemplateFindingSeverity
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines, write_bundle
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

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

    @pytest.mark.usefixtures("stub_engines")
    async def test_an_html_template_file_that_is_not_utf8_is_refused_naming_it(self, tmp_path: Path) -> None:
        """A template saved in another encoding is refused at load, naming the file, rather than crashing the load."""
        (tmp_path / "invoice.html").write_bytes("<p>Facture émise</p>".encode("latin-1"))
        bundle_path = write_bundle(directory=tmp_path, step_fields='format = "pdf"\ntemplate_file = "invoice.html"')

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        assert "could not read the template file 'invoice.html' as UTF-8 text" in str(exc_info.value.to_error_report().model_dump())

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

    async def test_an_anything_input_reaches_the_checker_with_an_undeclared_shape(self, tmp_path: Path, stub_engines: StubEngines) -> None:
        """An `Anything` input has no content class to describe, so the checker is told its shape is not declared."""
        (tmp_path / "invoice.docx").write_bytes(b"docx bytes")
        bundle_path = tmp_path / "invoice.mthds"
        bundle_path.write_text(
            PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP).replace(
                'inputs      = { invoice = "Invoice" }', 'inputs      = { invoice = "Invoice", thing = "Anything" }'
            ),
            encoding="utf-8",
        )

        await validate_bundle(mthds_file_path=bundle_path)

        (request,) = stub_engines.check_requests
        assert request.inputs["thing"].kind == InputShapeKind.ANY
        assert request.inputs["invoice"].kind == InputShapeKind.STRUCTURE

    async def test_warnings_alone_pass_and_print_nothing(self, tmp_path: Path, stub_engines: StubEngines, mocker: MockerFixture) -> None:
        """A warning is logged, not raised, and the dry run prints nothing.

        The line is the same for every finding, and the finding's own words and place ride as fields beside the step and its file.
        """
        warning_spy = mocker.spy(log, "warning")
        (tmp_path / "invoice.docx").write_bytes(b"docx bytes")
        bundle_path = write_bundle(directory=tmp_path, step_fields=_DOCX_TEMPLATE_STEP)
        stub_engines.findings = [
            TemplateFinding(severity=TemplateFindingSeverity.WARNING, message="The notes are never printed", location="the field notes on page 2")
        ]

        await validate_bundle(mthds_file_path=bundle_path)

        assert len(stub_engines.check_requests) == 1
        assert stub_engines.engine.jobs == []
        (finding_call,) = [
            call for call in warning_spy.call_args_list if call.args[0] == "The template check of a PipeDocGen found a warning in its template file"
        ]
        assert finding_call.kwargs["fields"] == {
            "pipe_code": "print_invoice",
            "template_file": "invoice.docx",
            "finding_message": "The notes are never printed",
            "finding_location": "the field notes on page 2",
        }
