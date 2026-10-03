"""The LLM worker refuses a prompt document whose known format its model does not read, as an input error.

A document format the model does not read used to raise `LLMCapabilityError`, a configuration error
that answers 500, although the file is the caller's and changes from run to run. It is now a
`PromptDocumentFormatError`, a content error in the input domain. `LLMCapabilityError` stays for a
model that reads no documents at all, which is the method author's choice of model. An unknown
format is left to the provider, and a document whose bytes identify nothing no longer raises.
"""

import base64

import pytest
from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.document.prompt_document import PromptDocument, PromptDocumentBase64, PromptDocumentBinary, PromptDocumentUri
from pipelex.cogt.exceptions import LLMCapabilityError, PromptDocumentFormatError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
STORED_DOCX = "pipelex-storage://org/uploads/brief.docx"
STORED_PDF = "pipelex-storage://org/uploads/brief.pdf"
MARKDOWN_BYTES = b"# Brief\n\nNothing a sniffer can recognise."


class _CallCountingLLMWorker(LLMWorkerAbstract):
    """A worker whose provider half only counts the calls that reach it."""

    def __init__(self, *, inference_model: InferenceModelSpec) -> None:
        LLMWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=None)
        self.nb_provider_calls = 0

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        self.nb_provider_calls += 1
        return "answer"

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        self.nb_provider_calls += 1
        return schema.model_validate({})


def _make_worker(*, inputs: list[str]) -> _CallCountingLLMWorker:
    inference_model = InferenceModelSpec(
        backend_name="openai",
        name="gpt-docs-test",
        sdk="openai",
        model_type=ModelType.LLM,
        model_id="gpt-docs-test-id",
        inputs=inputs,
        outputs=["text"],
        costs={CostCategory.INPUT: 1, CostCategory.OUTPUT: 2},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return _CallCountingLLMWorker(inference_model=inference_model)


def _make_llm_job(*, user_documents: list[PromptDocument]) -> LLMJob:
    return LLMJob(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-document-format", storage_scope="test/scope", read_scope=None),
            pipe_code="summarize_brief",
        ),
        llm_prompt=LLMPrompt(user_text="Summarize the brief.", user_documents=user_documents),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestLLMWorkerDocumentFormat:
    async def test_a_document_format_the_model_does_not_read_is_an_input_error(self):
        worker = _make_worker(inputs=["text", "pdf"])
        documents: list[PromptDocument] = [
            PromptDocumentUri(uri=STORED_PDF, mime_type="application/pdf"),
            PromptDocumentUri(uri=STORED_DOCX, mime_type=DOCX_MIME),
        ]

        with pytest.raises(PromptDocumentFormatError) as exc_info:
            await worker.gen_text(llm_job=_make_llm_job(user_documents=documents))

        assert str(exc_info.value) == (
            "Prompt document 2 given to model 'gpt-docs-test' is a Word document (.docx), which it does not read: it reads PDF."
        )
        assert exc_info.value.to_error_report().error_domain == ErrorDomain.INPUT
        assert worker.nb_provider_calls == 0

    async def test_a_model_reading_no_documents_is_still_a_capability_error(self):
        worker = _make_worker(inputs=["text", "images"])

        with pytest.raises(LLMCapabilityError, match="does not support documents"):
            await worker.gen_text(llm_job=_make_llm_job(user_documents=[PromptDocumentUri(uri=STORED_PDF, mime_type="application/pdf")]))

    @pytest.mark.parametrize(
        "document",
        [
            PromptDocumentUri(uri=STORED_DOCX, mime_type=DOCX_MIME),
            PromptDocumentUri(uri=STORED_DOCX),
            PromptDocumentBase64(base64_data=base64.b64encode(MARKDOWN_BYTES).decode("ascii")),
            PromptDocumentBinary(raw_bytes=MARKDOWN_BYTES),
        ],
        ids=["declared-format", "unknown-uri", "unidentifiable-base64", "unidentifiable-binary"],
    )
    async def test_a_readable_or_unknown_format_reaches_the_provider(self, document: PromptDocument):
        worker = _make_worker(inputs=["text", "pdf", "docx"])

        assert await worker.gen_text(llm_job=_make_llm_job(user_documents=[document])) == "answer"
        assert worker.nb_provider_calls == 1
