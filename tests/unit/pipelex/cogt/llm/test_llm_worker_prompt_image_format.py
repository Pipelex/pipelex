"""The LLM worker refuses a prompt image whose known format is not an image, before the provider sees it.

Run setup refuses a non-image given to an Image input, but a run can produce its own images mid-run,
and those never pass through setup. The worker is the second line: a prompt image whose format is
known and is not the image family raises `PromptImageFormatError`, which is a content error and so
in the input domain. An image whose format is unknown is left to the provider, as before.
"""

import base64
from pathlib import Path

import pytest
from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBase64, PromptImageBinary, PromptImageUri
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

PDF_BYTES = Path("tests/data/documents/solar_system.pdf").read_bytes()
PNG_BYTES = Path("tests/data/images/logo-tiny.png").read_bytes()
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
STORED_URI = "pipelex-storage://org/run/assets/figure.png"


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


def _make_worker() -> _CallCountingLLMWorker:
    inference_model = InferenceModelSpec(
        backend_name="openai",
        name="gpt-vision-test",
        sdk="openai",
        model_type=ModelType.LLM,
        model_id="gpt-vision-test-id",
        inputs=["text", "images"],
        outputs=["text"],
        costs={CostCategory.INPUT: 1, CostCategory.OUTPUT: 2},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return _CallCountingLLMWorker(inference_model=inference_model)


def _make_llm_job(*, user_images: list[PromptImage]) -> LLMJob:
    return LLMJob(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-image-format", storage_scope="test/scope", read_scope=None),
            pipe_code="describe_figure",
        ),
        llm_prompt=LLMPrompt(user_text="Describe the figure.", user_images=user_images),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestLLMWorkerPromptImageFormat:
    @pytest.mark.parametrize(
        "pdf_image",
        [
            PromptImageBase64(base64_data=base64.b64encode(PDF_BYTES).decode("ascii")),
            PromptImageBinary(raw_bytes=PDF_BYTES),
            PromptImageUri(uri=STORED_URI, mime_type="application/pdf"),
        ],
    )
    async def test_an_image_produced_mid_run_whose_bytes_are_a_pdf_is_refused(self, pdf_image: PromptImage):
        worker = _make_worker()
        png_image = PromptImageBinary(raw_bytes=PNG_BYTES)

        with pytest.raises(PromptImageFormatError) as exc_info:
            await worker.gen_text(llm_job=_make_llm_job(user_images=[png_image, pdf_image]))

        assert str(exc_info.value) == ("Prompt image 2 given to model 'gpt-vision-test' is a PDF document (application/pdf), not an image.")
        assert exc_info.value.to_error_report().error_domain == ErrorDomain.INPUT
        assert worker.nb_provider_calls == 0

    @pytest.mark.parametrize(
        "image",
        [
            PromptImageBinary(raw_bytes=PNG_BYTES),
            PromptImageBase64(base64_data=base64.b64encode(PNG_BYTES).decode("ascii")),
            PromptImageUri(uri=STORED_URI, mime_type="image/png"),
            PromptImageUri(uri=STORED_URI),
            PromptImageBinary(raw_bytes=SVG_BYTES),
        ],
    )
    async def test_an_image_or_an_unknown_format_reaches_the_provider(self, image: PromptImage):
        worker = _make_worker()

        assert await worker.gen_text(llm_job=_make_llm_job(user_images=[image])) == "answer"
        assert worker.nb_provider_calls == 1
