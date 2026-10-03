"""A PDF given to an Image input is refused by run setup, before any pipe runs, as an input error an API answers with 422.

The proof-lab scenario: a referral letter scanned as a PDF, given to an input whose concept refines
`Image`. It used to pass preparation and fail at the first model call, in the provider's words and
with no error domain. Run setup is where an API's `/start` runs, so a refusal here is the answer
the caller receives synchronously.
"""

import base64
from pathlib import Path

import pytest

from pipelex.base_exceptions import ErrorDomain, error_domain_to_http_status
from pipelex.config import get_config
from pipelex.pipeline.exceptions import PipelineInputNotAnImageError
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup

PDF_BYTES = Path("tests/data/documents/solar_system.pdf").read_bytes()
PNG_BYTES = Path("tests/data/images/logo-tiny.png").read_bytes()

_REFERRAL_MTHDS = """
domain = "referral_image_format_test"
description = "A method reading a referral letter given as an image"

[concept.ReferralLetter]
description = "A scanned referral letter"
refines = "Image"

[pipe.read_referral]
type = "PipeLLM"
description = "Read the referral letter"
inputs = { referral_letter = "ReferralLetter", photo = "Image" }
output = "Text"
prompt = "Summarize the referral letter: $referral_letter. Describe the photo: $photo."
"""


def _data_url(*, mime_type: str, raw_bytes: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"


@pytest.mark.asyncio(loop_scope="class")
class TestPipelineRunSetupImageFormat:
    @pytest.mark.parametrize(
        ("referral_bytes", "photo_bytes", "refused_input"),
        [
            (PDF_BYTES, PNG_BYTES, "referral_letter"),
            (PNG_BYTES, PDF_BYTES, "photo"),
        ],
    )
    async def test_a_pdf_in_an_image_input_is_refused_at_setup_with_422(self, referral_bytes: bytes, photo_bytes: bytes, refused_input: str):
        """Both a concept refining Image and the native Image itself are checked."""
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)

        with pytest.raises(PipelineInputNotAnImageError) as exc_info:
            await pipeline_run_setup(
                storage_scope="test/scope",
                read_scope=None,
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_REFERRAL_MTHDS],
                pipe_code="read_referral",
                inputs={
                    "referral_letter": _data_url(mime_type="image/png", raw_bytes=referral_bytes),
                    "photo": _data_url(mime_type="image/png", raw_bytes=photo_bytes),
                },
            )

        report = exc_info.value.to_error_report()
        assert report.error_domain == ErrorDomain.INPUT
        assert error_domain_to_http_status(report.error_domain) == 422
        assert report.http_status == 422
        assert f"Input '{refused_input}' expects an image, but the file is a PDF document (application/pdf)" in report.message

    async def test_images_pass_setup(self):
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)

        pipe_job, _pipeline_run_id, _ = await pipeline_run_setup(
            storage_scope="test/scope",
            read_scope=None,
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_REFERRAL_MTHDS],
            pipe_code="read_referral",
            inputs={
                "referral_letter": _data_url(mime_type="image/png", raw_bytes=PNG_BYTES),
                "photo": _data_url(mime_type="image/png", raw_bytes=PNG_BYTES),
            },
        )

        assert pipe_job.working_memory is not None
        referral_letter = pipe_job.working_memory.get_stuff_as_image(name="referral_letter")
        assert referral_letter.mime_type == "image/png"
