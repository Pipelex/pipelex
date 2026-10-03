"""The extract worker refuses a file whose known format its model does not read, before the provider sees it.

The model is fixed by the method and reads the formats it declares; the file changes from run to run,
so a format the model does not read is the caller's input fault, an `ExtractInputFormatError` in the
input domain, and its message names the input, the format, the model and what that model reads. An
unknown format is left to the provider. A web-page model given an http(s) URL fetches the page itself,
so its format is not checked.
"""

import pytest
from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import ExtractCapabilityError, ExtractInputFormatError
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.job_metadata import JobMetadata, RunMetadata

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
STORED_DOCX = "pipelex-storage://org/uploads/transcript.docx"


class _CallCountingExtractWorker(ExtractWorkerAbstract):
    """An extract worker whose provider half only counts the calls that reach it."""

    def __init__(self, *, inference_model: InferenceModelSpec) -> None:
        super().__init__(extra_config={}, inference_model=inference_model)
        self.nb_provider_calls = 0

    @override
    async def _extract_pages(self, extract_job: ExtractJob) -> ExtractOutput:
        self.nb_provider_calls += 1
        return ExtractOutput(pages={0: Page(text="page text")})


def _make_worker(*, inputs: list[str]) -> _CallCountingExtractWorker:
    inference_model = InferenceModelSpec(
        backend_name="test",
        name="azure-document-intelligence",
        sdk="test_extract",
        model_type=ModelType.TEXT_EXTRACTOR,
        model_id="prebuilt-layout",
        inputs=inputs,
        outputs=["text"],
        costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 1.0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return _CallCountingExtractWorker(inference_model=inference_model)


def _make_job(*, extract_input: ExtractInput) -> ExtractJob:
    return ExtractJob(
        extract_input=extract_input,
        job_params=ExtractJobParams.make_default_extract_job_params(),
        job_config=ExtractJobConfig(),
        job_report=ExtractJobReport(),
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="test-user", pipeline_run_id="test-run")
        ),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestExtractInputFormatCheck:
    async def test_a_docx_given_to_a_model_reading_pdf_and_images_is_refused(self):
        worker = _make_worker(inputs=["pdf", "image"])
        job = _make_job(extract_input=ExtractInput(document_uri=STORED_DOCX, mime_type=DOCX_MIME, input_name="transcripts[0]"))

        with pytest.raises(ExtractInputFormatError) as exc_info:
            await worker.extract_pages(extract_job=job)

        assert str(exc_info.value) == (
            "Input 'transcripts[0]' is a Word document (.docx), which model 'azure-document-intelligence' cannot extract: "
            "it reads PDF and images. Give a file in one of those formats, or use an extract model that reads this one."
        )
        assert exc_info.value.to_error_report().error_domain == ErrorDomain.INPUT
        assert worker.nb_provider_calls == 0

    async def test_a_file_with_no_input_name_is_named_as_the_file_to_extract(self):
        worker = _make_worker(inputs=["pdf"])
        job = _make_job(extract_input=ExtractInput(document_uri=STORED_DOCX, mime_type=DOCX_MIME))

        with pytest.raises(ExtractInputFormatError, match=r"^The file to extract is a Word document \(\.docx\), which model"):
            await worker.extract_pages(extract_job=job)

    @pytest.mark.parametrize(
        ("inputs", "extract_input"),
        [
            (["pdf", "docx", "image"], ExtractInput(document_uri=STORED_DOCX, mime_type=DOCX_MIME, input_name="transcript")),
            (["pdf"], ExtractInput(document_uri=STORED_DOCX, input_name="transcript")),
            (["pdf"], ExtractInput(document_uri=STORED_DOCX, mime_type="application/octet-stream", input_name="transcript")),
            (["web_page"], ExtractInput(document_uri="https://example.com/report", mime_type="application/pdf", input_name="page")),
            (["pdf", "image"], ExtractInput(image_uri="pipelex-storage://org/uploads/scan.png", mime_type="image/png", input_name="scan")),
            (["pdf", "image"], ExtractInput(document_uri="pipelex-storage://org/uploads/scan.png", mime_type="image/png", input_name="scan")),
        ],
        ids=["declared-format", "unknown-format", "generic-format", "web-page-url", "image-as-image", "image-as-document"],
    )
    async def test_a_readable_or_unknown_format_reaches_the_provider(self, inputs: list[str], extract_input: ExtractInput):
        worker = _make_worker(inputs=inputs)

        output = await worker.extract_pages(extract_job=_make_job(extract_input=extract_input))

        assert output.pages[0].text == "page text"
        assert worker.nb_provider_calls == 1

    async def test_a_web_page_model_given_a_stored_file_is_format_checked(self):
        """Only an http(s) URL is the web-page model's to fetch; a stored file of a format it does not read is refused."""
        worker = _make_worker(inputs=["web_page"])
        job = _make_job(extract_input=ExtractInput(document_uri=STORED_DOCX, mime_type=DOCX_MIME, input_name="page"))

        with pytest.raises(ExtractInputFormatError, match=r"it reads web pages\."):
            await worker.extract_pages(extract_job=job)

    async def test_a_model_reading_no_images_given_an_image_input_is_still_a_capability_error(self):
        """Choosing a model that extracts no images for an Image input is the method author's choice, not the caller's input."""
        worker = _make_worker(inputs=["pdf"])
        job = _make_job(extract_input=ExtractInput(image_uri="pipelex-storage://org/uploads/scan.png", mime_type="image/png", input_name="scan"))

        with pytest.raises(ExtractCapabilityError):
            await worker.extract_pages(extract_job=job)
