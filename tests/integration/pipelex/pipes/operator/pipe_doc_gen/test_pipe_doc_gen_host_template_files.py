import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import DisclosureMode
from pipelex.cogt.doc_gen.template_check import TemplateFinding, TemplateFindingSeverity
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipeline.exceptions import HostLibraryLoadRefusalError, ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import HOST_LIBRARY_FILE_PLACEHOLDER
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines, write_bundle
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

_HOST_TEMPLATE_FILE = "templates/host-invoice.docx"


@pytest.fixture(autouse=True)
def restore_the_outer_library() -> Iterator[None]:
    """Tear down whatever library a refused validation left current, and restore the one the test started in."""
    outer_library_id = get_current_library_id_or_none()
    yield
    leaked_library_id = get_current_library_id_or_none()
    if leaked_library_id is not None and leaked_library_id != outer_library_id:
        get_library_manager().teardown(library_id=leaked_library_id)
    if outer_library_id is not None:
        set_current_library(library_id=outer_library_id)
    else:
        clear_current_library()


async def _caller_verdict(*, mthds_content: str, host_dir: Path) -> str:
    """The invalid verdict, as JSON, of submitted content validated beside a host's library directory."""
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundles_in_process(mthds_contents=[mthds_content], library_dirs=[host_dir])
    return exc_info.value.to_error_report().model_dump_json()


async def _host_fault_strict_payload(*, mthds_content: str, host_dir: Path) -> str:
    """The STRICT payload, as JSON, of a host's library refusing to load beside submitted content: the deployment's fault."""
    with pytest.raises(HostLibraryLoadRefusalError) as exc_info:
        await validate_bundles_in_process(mthds_contents=[mthds_content], library_dirs=[host_dir])
    report = exc_info.value.to_error_report()
    assert report.code == CoreCode.RUNTIME_MISCONFIGURED
    return json.dumps(report.to_dict(disclosure_mode=DisclosureMode.STRICT))


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenHostTemplateFiles:
    async def test_a_host_step_s_template_check_error_names_no_template_file(self, tmp_path: Path, stub_engines: StubEngines) -> None:
        """A caller's sequence runs a host step whose template the engine refuses: the verdict says so without naming the file."""
        (tmp_path / "templates").mkdir()
        (tmp_path / _HOST_TEMPLATE_FILE).write_bytes(b"docx bytes")
        write_bundle(directory=tmp_path, step_fields=f'format = "docx"\ntemplate_file = "{_HOST_TEMPLATE_FILE}"')
        stub_engines.findings = [TemplateFinding(severity=TemplateFindingSeverity.ERROR, message="The tag {{ invoice.totl }} names no field")]

        verdict = await _caller_verdict(mthds_content=PipeDocGenTestData.CALLER_BUNDLE_MTHDS, host_dir=tmp_path)

        assert "invoice.totl" in verdict
        assert HOST_LIBRARY_FILE_PLACEHOLDER in verdict
        assert "host-invoice" not in verdict

    @pytest.mark.parametrize(
        "step_fields",
        [
            f'format = "docx"\ntemplate_file = "{_HOST_TEMPLATE_FILE}"',
            'format = "docx"\ntemplate_file = "templates/host-invoice.xlsx"',
        ],
        ids=["missing_file", "wrong_suffix"],
    )
    @pytest.mark.usefixtures("stub_engines")
    async def test_a_host_step_s_load_refusal_names_no_template_file(self, tmp_path: Path, step_fields: str) -> None:
        """A host step refused while the host's library loads beside submitted content is the host's fault, naming no template file of it."""
        write_bundle(directory=tmp_path, step_fields=step_fields)

        strict_payload = await _host_fault_strict_payload(mthds_content=PipeDocGenTestData.CALLER_BUNDLE_MTHDS, host_dir=tmp_path)

        assert "host-invoice" not in strict_payload
        assert str(tmp_path) not in strict_payload

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_host_step_naming_its_template_file_by_an_absolute_path_names_no_host_path(self, tmp_path: Path) -> None:
        """A host step naming its template file by an absolute path is the host's fault, whose STRICT payload carries nothing of the host's disk."""
        (tmp_path / "invoice.docx").write_bytes(b"docx bytes")
        write_bundle(directory=tmp_path, step_fields=f'format = "docx"\ntemplate_file = "{(tmp_path / "invoice.docx").resolve()}"')

        strict_payload = await _host_fault_strict_payload(mthds_content=PipeDocGenTestData.CALLER_BUNDLE_MTHDS, host_dir=tmp_path)

        assert str(tmp_path.resolve()) not in strict_payload
        assert str(tmp_path) not in strict_payload

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_caller_step_keeps_naming_a_template_file_a_host_step_names_too(self, tmp_path: Path) -> None:
        """A template file the submitted content names is the caller's own, so its refusal keeps naming it."""
        (tmp_path / "invoice.docx").write_bytes(b"docx bytes")
        write_bundle(directory=tmp_path, step_fields='format = "docx"\ntemplate_file = "invoice.docx"')
        own_bundle = PipeDocGenTestData.bundle(step_fields='format = "docx"\ntemplate_file = "invoice.docx"').replace("doc_gen_tests", "doc_gen_own")

        verdict = await _caller_verdict(mthds_content=own_bundle, host_dir=tmp_path)

        assert "which was not supplied with its bundle" in verdict
        assert "'invoice.docx'" in verdict
        assert HOST_LIBRARY_FILE_PLACEHOLDER not in verdict
