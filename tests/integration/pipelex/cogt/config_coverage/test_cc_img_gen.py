import pytest

from pipelex import log, pretty_print
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_job_factory import ImgGenJobFactory
from pipelex.hub import get_img_gen_worker
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.img_gen
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestConfigCoverageImgGen:
    async def test_gen_image(self, job_metadata: JobMetadata, img_gen_combo: ModelCombo, img_gen_job_params: ImgGenJobParams) -> None:
        """Verify that image generation works for this Portkey config."""
        log.info(f"Config coverage: testing img_gen '{img_gen_combo.handle}'")
        img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt_contents(
            positive_text="a small red bird on a branch",
            negative_text=None,
            job_metadata=job_metadata,
            img_gen_job_params=img_gen_job_params,
        )
        generated_image_raw_details = await img_gen_worker.gen_image(img_gen_job=img_gen_job)
        assert generated_image_raw_details
        pretty_print(generated_image_raw_details, title=f"Generated image for '{img_gen_combo.handle}'")
