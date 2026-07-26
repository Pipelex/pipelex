import pytest

from pipelex import pretty_print, pretty_print_url
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_job_factory import ImgGenJobFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.service_hub import get_img_gen_worker
from pipelex.tools.misc.image_utils import ImageFormat
from tests.integration.pipelex.fixtures.img_gen_fixtures import skip_if_img_gen_params_unsupported
from tests.integration.pipelex.fixtures.model_combo import ModelCombo
from tests.integration.pipelex.test_data import ImageGenTestCases

PRIMARY_ID = "id_1"
SECONDARY_ID = "id_2"


@pytest.mark.img_gen
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageGeneration:
    @pytest.mark.parametrize(("topic", "positive_text", "negative_text"), ImageGenTestCases.IMAGE_GEN_PROMPT_CONTENTS)
    async def test_img_gen_single_opaque(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        img_gen_job_params: ImgGenJobParams,
        topic: str,
        positive_text: str,
        negative_text: str | None,
        generated_content_factory: GeneratedContentFactory,
    ):
        pretty_print(f"Testing image generation with handle '{img_gen_combo.handle}', output format '{img_gen_job_params.output_format}'")
        pretty_print(f"Positive text: {positive_text}\nNegative text: {negative_text}", title="Prompts")
        img_gen_worker_async = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        skip_if_img_gen_params_unsupported(img_gen_worker_async.inference_model, img_gen_job_params)
        img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt_contents(
            positive_text=positive_text,
            negative_text=negative_text,
            job_metadata=job_metadata,
            img_gen_job_params=img_gen_job_params,
        )
        generated_image_raw_details = await img_gen_worker_async.gen_image(
            img_gen_job=img_gen_job,
        )
        pretty_print(generated_image_raw_details, title=f"Generated image raw details for topic '{topic}'")
        image_content = await generated_content_factory.make_image_content(
            primary_id=PRIMARY_ID,
            secondary_id=SECONDARY_ID,
            raw_details=generated_image_raw_details,
        )
        pretty_print(image_content, title=f"Image content for topic '{topic}'")
        assert image_content.public_url is not None
        pretty_print_url(image_content.public_url, title=f"Image URL for topic '{topic}'")

    @pytest.mark.parametrize(("topic", "positive_text", "negative_text"), ImageGenTestCases.IMAGE_GEN_PROMPT_CONTENTS)
    async def test_img_gen_single_transparent(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        topic: str,
        positive_text: str,
        negative_text: str | None,
        generated_content_factory: GeneratedContentFactory,
    ):
        img_gen_worker_async = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            is_raw=None,
            background=Background.TRANSPARENT,
            output_format=ImageFormat.PNG,
        )
        skip_if_img_gen_params_unsupported(img_gen_worker_async.inference_model, img_gen_job_params)
        img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt_contents(
            positive_text=positive_text,
            negative_text=negative_text,
            job_metadata=job_metadata,
            img_gen_job_params=img_gen_job_params,
        )
        generated_image_raw_details = await img_gen_worker_async.gen_image(
            img_gen_job=img_gen_job,
        )
        pretty_print(generated_image_raw_details, title=f"Generated image raw details for topic '{topic}'")
        image_content = await generated_content_factory.make_image_content(
            primary_id=PRIMARY_ID,
            secondary_id=SECONDARY_ID,
            raw_details=generated_image_raw_details,
        )
        pretty_print(image_content, title=f"Image content for topic '{topic}'")
        assert image_content.public_url is not None
        pretty_print_url(image_content.public_url, title=f"Image URL for topic '{topic}'")

    @pytest.mark.parametrize(("topic", "positive_text", "negative_text"), ImageGenTestCases.IMAGE_GEN_PROMPT_CONTENTS)
    async def test_img_gen_multiple(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        img_gen_job_params: ImgGenJobParams,
        topic: str,
        positive_text: str,
        negative_text: str | None,
        generated_content_factory: GeneratedContentFactory,
    ):
        img_gen_worker_async = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        skip_if_img_gen_params_unsupported(img_gen_worker_async.inference_model, img_gen_job_params)
        img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt_contents(
            positive_text=positive_text,
            negative_text=negative_text,
            job_metadata=job_metadata,
            img_gen_job_params=img_gen_job_params,
        )
        generated_image_raw_details_list = await img_gen_worker_async.gen_image_list(
            img_gen_job=img_gen_job,
            nb_images=3,
        )
        pretty_print(generated_image_raw_details_list, title=f"Images generated by '{img_gen_combo.handle}' for topic '{topic}'")
        image_content_list = [
            (
                await generated_content_factory.make_image_content(
                    primary_id=PRIMARY_ID,
                    secondary_id=SECONDARY_ID,
                    raw_details=generated_image_raw_details,
                )
            )
            for generated_image_raw_details in generated_image_raw_details_list
        ]
        pretty_print(image_content_list, title=f"Image contents for topic '{topic}'")
        for image_index, image in enumerate(image_content_list):
            assert image.public_url is not None
            pretty_print_url(image.public_url, title=f"Image URL #{image_index}")
