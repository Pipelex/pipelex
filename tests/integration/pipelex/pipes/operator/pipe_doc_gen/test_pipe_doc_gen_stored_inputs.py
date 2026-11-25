from uuid import uuid4

import pytest

from pipelex.cogt.doc_gen.doc_gen_format import DocGenSource
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import get_storage_provider
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.cases import PipeDocGenTestData
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines

READ_SCOPE = "org_doc_gen"
# Past the default inline threshold of 4096 bytes, and free of anything an HTML render would escape.
NOTES_TEXT = "The notes the caller stored, one sentence after another. " * 100
_DOCX_BYTES = b"PK docx template bytes"


def _bundle_with_notes(*, step_fields: str) -> str:
    return PipeDocGenTestData.bundle(step_fields=step_fields).replace(
        'inputs      = { invoice = "Invoice" }', 'inputs      = { invoice = "Invoice", notes = "Text" }'
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenStoredInputs:
    @pytest.mark.parametrize(
        ("step_fields", "submitted_files", "expected_source"),
        [
            pytest.param('format = "pdf"', None, DocGenSource.LAYOUT, id="layout"),
            pytest.param('format = "pdf"\ntemplate = "<p>$notes</p>"', None, DocGenSource.HTML, id="inline_html_template"),
            pytest.param(
                'format = "pdf"\ntemplate_file = "notes.html"', {"notes.html": b"<p>$notes</p>"}, DocGenSource.HTML, id="html_template_file"
            ),
            pytest.param(
                'format = "docx"\ntemplate_file = "notes.docx"', {"notes.docx": _DOCX_BYTES}, DocGenSource.TEMPLATE_FILE, id="office_template"
            ),
        ],
    )
    async def test_a_stored_text_input_is_printed_as_its_text(
        self, stub_engines: StubEngines, step_fields: str, submitted_files: dict[str, bytes] | None, expected_source: DocGenSource
    ) -> None:
        """A Text the caller gives by URL, unloaded until a step reads it, reaches the engine as its text from every source."""
        notes_url = await get_storage_provider().store(
            data=NOTES_TEXT.encode("utf-8"), key=f"{READ_SCOPE}/uploads/{uuid4().hex}/notes.txt", content_type="text/plain; charset=utf-8"
        )

        await PipelexMTHDSProtocol(
            storage_scope=f"{READ_SCOPE}/mt_doc_gen/run_{uuid4().hex}", read_scope=READ_SCOPE, submitted_files=submitted_files
        ).execute(
            mthds_contents=[_bundle_with_notes(step_fields=step_fields)],
            inputs={**PipeDocGenTestData.INVOICE_INPUTS, "notes": {"concept": "Text", "content": {"url": notes_url}}},
        )

        (job,) = stub_engines.engine.jobs
        assert job.source == expected_source
        match expected_source:
            case DocGenSource.LAYOUT:
                assert job.layout is not None
                assert NOTES_TEXT.strip() in job.layout.model_dump_json()
            case DocGenSource.HTML:
                assert job.html == f"<p>{NOTES_TEXT}</p>"
            case DocGenSource.TEMPLATE_FILE:
                assert job.data["notes"] == NOTES_TEXT
