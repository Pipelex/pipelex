"""Run setup refuses a run whose file inputs are certain to reach a consumer that cannot read their format.

The first proof-lab scenario: Word transcripts batched into a `PipeExtract` whose model reads PDF
only. They used to fail the run at the extraction, after it started; run setup now refuses the run
before any pipe runs, with one input error naming every transcript. A consumer reached only through
a condition is not certain, so the run starts, and the operator refuses the file when it gets there.
"""

import base64
import re
import zipfile
from pathlib import Path

import pytest

from pipelex.base_exceptions import DisclosureMode, ErrorDomain
from pipelex.cogt.exceptions import ExtractInputFormatError
from pipelex.config import get_config
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_router
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipeline.exceptions import PipelineInputFormatUnsupportedError
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from tests.cases import DocumentTestCases

DOCX_BYTES = Path(DocumentTestCases.DOCX_FILE_PATH_1).read_bytes()
PDF_BYTES = Path(DocumentTestCases.PDF_FILE_PATH_3).read_bytes()

_TRANSCRIPTS_MTHDS = """
domain = "consumer_check_transcripts"
description = "Extract interview transcripts"

[pipe.extract_transcripts]
type = "PipeSequence"
description = "Extract every transcript"
inputs = { transcripts = "Document[]" }
output = "Page[]"
steps = [{ pipe = "extract_transcript", batch_over = "transcripts", batch_as = "transcript", result = "pages" }]

[pipe.extract_transcript]
type = "PipeExtract"
description = "Extract one transcript"
inputs = { transcript = "Document" }
output = "Page[]"
model = "pypdfium2-extract-pdf"
"""

_SINGLE_TRANSCRIPT_MTHDS = """
domain = "consumer_check_single"
description = "Extract one transcript with either model"

[pipe.extract_with_pdf_model]
type = "PipeExtract"
description = "Extract the transcript with a model reading PDF only"
inputs = { transcript = "Document" }
output = "Page[]"
model = "pypdfium2-extract-pdf"

[pipe.extract_with_word_model]
type = "PipeExtract"
description = "Extract the transcript with a model reading Word files"
inputs = { transcript = "Document" }
output = "Page[]"
model = "docling-extract-text"
"""

_CONDITIONAL_MTHDS = """
domain = "consumer_check_conditional"
description = "Extract a transcript in one mode only"

[pipe.maybe_extract]
type = "PipeCondition"
description = "Extract the transcript when asked to"
inputs = { mode = "Text", transcript = "Document" }
output = "Page[]"
expression = "mode"
default_outcome = "fail"

[pipe.maybe_extract.outcomes]
extract = "extract_transcript"

[pipe.extract_transcript]
type = "PipeExtract"
description = "Extract one transcript"
inputs = { transcript = "Document" }
output = "Page[]"
model = "pypdfium2-extract-pdf"
"""


def _data_url(*, mime_type: str, raw_bytes: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"


def _write_late_entry_docx(*, path: Path) -> Path:
    """Rewrite the Word fixture with a large custom part first, so the sniffer sees only a zip container."""
    with zipfile.ZipFile(DocumentTestCases.DOCX_FILE_PATH_1) as source, zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as target:
        entry_names = source.namelist()
        leading = [entry_name for entry_name in entry_names if entry_name in {"[Content_Types].xml", "_rels/.rels"}]
        for entry_name in leading:
            target.writestr(entry_name, source.read(entry_name))
        target.writestr("customXml/item1.xml", "<data>" + "x" * 12_000 + "</data>")
        for entry_name in entry_names:
            if entry_name not in leading:
                target.writestr(entry_name, source.read(entry_name))
    return path


def _find_in_cause_chain(error: BaseException, *, error_class: type[BaseException]) -> BaseException | None:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, error_class):
            return current
        current = current.__cause__ or current.__context__
    return None


@pytest.mark.asyncio(loop_scope="class")
class TestPipelineRunSetupConsumerCheck:
    async def test_word_transcripts_batched_into_a_pdf_extractor_are_refused_before_the_run(self):
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        docx_url = _data_url(mime_type="application/octet-stream", raw_bytes=DOCX_BYTES)

        with pytest.raises(PipelineInputFormatUnsupportedError) as exc_info:
            await pipeline_run_setup(
                storage_scope="test/scope",
                read_scope=None,
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_TRANSCRIPTS_MTHDS],
                pipe_code="extract_transcripts",
                inputs={"transcripts": {"concept": "native.Document", "content": [{"url": docx_url}, {"url": docx_url}, {"url": docx_url}]}},
            )

        report = exc_info.value.to_error_report()
        assert report.error_domain == ErrorDomain.INPUT
        assert report.http_status == 422
        message = exc_info.value.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)["message"]
        for index in range(3):
            assert (
                f"Input 'transcripts[{index}]' is a Word document (.docx): pipe 'extract_transcript' extracts it "
                "with model 'pypdfium2-extract-pdf', which reads PDF." in message
            )
        assert message.endswith("Give a file in a format its model reads, or use a model that reads this format.")

    async def test_a_pdf_among_the_transcripts_is_not_named(self):
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)

        with pytest.raises(PipelineInputFormatUnsupportedError) as exc_info:
            await pipeline_run_setup(
                storage_scope="test/scope",
                read_scope=None,
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_TRANSCRIPTS_MTHDS],
                pipe_code="extract_transcripts",
                inputs={
                    "transcripts": {
                        "concept": "native.Document",
                        "content": [
                            {"url": _data_url(mime_type="application/pdf", raw_bytes=PDF_BYTES)},
                            {"url": _data_url(mime_type="application/octet-stream", raw_bytes=DOCX_BYTES)},
                        ],
                    }
                },
            )

        assert "transcripts[1]" in str(exc_info.value)
        assert "transcripts[0]" not in str(exc_info.value)

    async def test_pdf_transcripts_pass_setup(self):
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        pdf_url = _data_url(mime_type="application/pdf", raw_bytes=PDF_BYTES)

        pipe_job, _pipeline_run_id, _ = await pipeline_run_setup(
            storage_scope="test/scope",
            read_scope=None,
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_TRANSCRIPTS_MTHDS],
            pipe_code="extract_transcripts",
            inputs={"transcripts": {"concept": "native.Document", "content": [{"url": pdf_url}]}},
        )

        assert pipe_job.pipe.code == "extract_transcripts"

    @pytest.mark.parametrize(
        ("pipe_code", "declared_mime_type", "expected_refusal"),
        [
            ("extract_with_word_model", None, None),
            ("extract_with_word_model", "application/zip", None),
            (
                "extract_with_pdf_model",
                None,
                "Input 'transcript' is a Word document (.docx): pipe 'extract_with_pdf_model' extracts it with model 'pypdfium2-extract-pdf'",
            ),
        ],
    )
    async def test_a_word_file_the_sniffer_sees_only_as_a_zip_is_known_by_its_name(
        self, tmp_path: Path, pipe_code: str, declared_mime_type: str | None, expected_refusal: str | None
    ):
        """The file's `.docx` name says what the zip holds, even over a declared bare zip, so the model reading Word files takes it."""
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        docx_path = _write_late_entry_docx(path=tmp_path / "interview.docx")
        content: dict[str, str] = {"url": str(docx_path)}
        if declared_mime_type is not None:
            content["mime_type"] = declared_mime_type
        setup = pipeline_run_setup(
            storage_scope="test/scope",
            read_scope=None,
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_SINGLE_TRANSCRIPT_MTHDS],
            pipe_code=pipe_code,
            inputs={"transcript": {"concept": "native.Document", "content": content}},
        )

        if expected_refusal is None:
            pipe_job, _pipeline_run_id, _ = await setup
            assert pipe_job.pipe.code == pipe_code
        else:
            with pytest.raises(PipelineInputFormatUnsupportedError, match=re.escape(expected_refusal)):
                await setup

    async def test_a_consumer_behind_a_condition_lets_the_run_start_and_the_operator_refuses(self):
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)

        pipe_job, _pipeline_run_id, _ = await pipeline_run_setup(
            storage_scope="test/scope",
            read_scope=None,
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_CONDITIONAL_MTHDS],
            pipe_code="maybe_extract",
            inputs={
                "mode": TextContent(text="extract"),
                "transcript": _data_url(mime_type="application/octet-stream", raw_bytes=DOCX_BYTES),
            },
        )

        # The operator's refusal arrives wrapped by the router that ran the pipe.
        with pytest.raises(PipeRouterError) as exc_info:
            await get_pipe_router().run(pipe_job=pipe_job)

        extract_refusal = _find_in_cause_chain(exc_info.value, error_class=ExtractInputFormatError)
        assert extract_refusal is not None, f"expected an ExtractInputFormatError in the cause chain, got {exc_info.value!r}"
        assert "Input 'transcript' is a Word document (.docx)" in str(extract_refusal)
