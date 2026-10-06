"""PipeExtract hands its extract worker the file's identified format and the name of the input it came from.

Run setup stamps every file input with the MIME type of its bytes; the operator passes it on in the
`ExtractInput`, beside the input's name, so the worker checks the format against its model instead
of guessing it again, and names the input when it refuses.
"""

import base64
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.config import get_config
from pipelex.pipe_operators.extract import pipe_extract as pipe_extract_module
from pipelex.pipe_operators.extract.pipe_extract import PipeExtract
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_BYTES = Path("tests/data/documents/CV-ELIAS-THORNE.docx").read_bytes()
PNG_BYTES = Path("tests/data/images/logo-tiny.png").read_bytes()

_EXTRACT_MTHDS = """
domain = "extract_input_format_test"
description = "Methods extracting a document and an image"

[pipe.extract_transcript]
type = "PipeExtract"
description = "Extract the transcript"
inputs = { transcript = "Document" }
output = "Page[]"
model = "docling-extract-text"

[pipe.extract_scan]
type = "PipeExtract"
description = "Extract the scan"
inputs = { scan = "Image" }
output = "Page[]"
"""


def _data_url(*, mime_type: str, raw_bytes: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"


class _ExtractInterruptedError(Exception):
    """Raised by the patched `run_extract` once it has captured its input, so no extraction runs."""


@pytest.mark.asyncio(loop_scope="class")
class TestPipeExtractInputFormat:
    @pytest.mark.parametrize(
        ("pipe_code", "input_name", "input_value", "expected_mime_type", "is_image"),
        [
            ("extract_transcript", "transcript", _data_url(mime_type="application/octet-stream", raw_bytes=DOCX_BYTES), DOCX_MIME, False),
            ("extract_scan", "scan", _data_url(mime_type="image/png", raw_bytes=PNG_BYTES), "image/png", True),
        ],
    )
    async def test_the_extract_input_carries_the_format_and_the_input_name(
        self,
        mocker: MockerFixture,
        pipe_code: str,
        input_name: str,
        input_value: str,
        expected_mime_type: str,
        is_image: bool,
    ):
        run_extract = mocker.patch.object(pipe_extract_module, "run_extract", side_effect=_ExtractInterruptedError)
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        pipe_job, _pipeline_run_id, _ = await pipeline_run_setup(
            storage_scope="test/scope",
            read_scope=None,
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_EXTRACT_MTHDS],
            pipe_code=pipe_code,
            inputs={input_name: input_value},
        )
        pipe = pipe_job.pipe
        assert isinstance(pipe, PipeExtract)
        assert pipe_job.working_memory is not None

        with pytest.raises(_ExtractInterruptedError):
            await pipe._live_run_operator_pipe(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
                job_metadata=pipe_job.job_metadata,
                working_memory=pipe_job.working_memory,
                pipe_run_params=pipe_job.pipe_run_params,
            )

        run_extract.assert_awaited_once()
        assert run_extract.await_args is not None
        extract_input = run_extract.await_args.kwargs["extract_input"]
        assert isinstance(extract_input, ExtractInput)
        assert extract_input.mime_type == expected_mime_type
        assert extract_input.input_name == input_name
        if is_image:
            assert extract_input.image_uri is not None
            assert extract_input.document_uri is None
        else:
            assert extract_input.document_uri is not None
            assert extract_input.image_uri is None
