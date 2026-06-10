from pipelex import log
from pipelex.cogt.content_generation.assignment_models import ImgGenAssignment
from pipelex.cogt.content_generation.dry_mock import dry_img_gen_image_contents
from pipelex.cogt.content_generation.exceptions import MockInferenceUnsupportedError
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_job_factory import ImgGenJobFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.hub import get_img_gen_worker


async def img_gen_single_image(img_gen_assignment: ImgGenAssignment) -> GeneratedImageRawDetails:
    if img_gen_assignment.job_metadata.is_mock_inference:
        error = MockInferenceUnsupportedError.for_operation("image generation (PipeImgGen)")
        raise error
    img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_assignment.img_gen_handle)
    img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt(
        img_gen_prompt=img_gen_assignment.img_gen_prompt,
        img_gen_job_params=img_gen_assignment.img_gen_job_params,
        img_gen_job_config=img_gen_assignment.img_gen_job_config,
        job_metadata=img_gen_assignment.job_metadata,
    )
    generated_image = await img_gen_worker.gen_image(img_gen_job=img_gen_job)
    log.verbose(f"generated_image:\n{generated_image}")
    return generated_image


async def img_gen_image_list(img_gen_assignment: ImgGenAssignment) -> list[GeneratedImageRawDetails]:
    if img_gen_assignment.job_metadata.is_mock_inference:
        error = MockInferenceUnsupportedError.for_operation("image generation (PipeImgGen)")
        raise error
    img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_assignment.img_gen_handle)
    img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt(
        img_gen_prompt=img_gen_assignment.img_gen_prompt,
        img_gen_job_params=img_gen_assignment.img_gen_job_params,
        img_gen_job_config=img_gen_assignment.img_gen_job_config,
        job_metadata=img_gen_assignment.job_metadata,
    )
    generated_image_list = await img_gen_worker.gen_image_list(
        img_gen_job=img_gen_job,
        nb_images=img_gen_assignment.nb_images,
    )
    log.verbose(f"generated_image_list:\n{generated_image_list}")
    return generated_image_list


async def img_gen_single_image_and_store(
    img_gen_assignment: ImgGenAssignment,
    generated_content_factory: GeneratedContentFactory,
) -> ImageContent:
    """Generate a single image and store it, returning an ImageContent with URLs (no raw binary data).

    The DRY branch sits at the ``*_and_store`` layer, above the raw provider leaf, so a dry run
    performs no storage IO — see the ``dry_mock`` module docstring (eng review D10). Do not
    "unify" it downward into the raw leaf.
    """
    if img_gen_assignment.cogt_run_params.run_mode.is_dry:
        return dry_img_gen_image_contents(img_gen_assignment)[0]
    generated_image = await img_gen_single_image(img_gen_assignment)
    image_content = await generated_content_factory.make_image_content(
        primary_id=img_gen_assignment.job_metadata.user_id,
        secondary_id=img_gen_assignment.job_metadata.pipeline_run_id,
        raw_details=generated_image,
    )
    image_content.source_prompt = img_gen_assignment.img_gen_prompt.positive_text
    image_content.source_negative_prompt = img_gen_assignment.img_gen_prompt.negative_text
    return image_content


async def img_gen_image_list_and_store(
    img_gen_assignment: ImgGenAssignment,
    generated_content_factory: GeneratedContentFactory,
) -> list[ImageContent]:
    """Generate multiple images and store them, returning ImageContent list with URLs (no raw binary data).

    DRY branch at the ``*_and_store`` layer — see ``img_gen_single_image_and_store`` (D10).
    """
    if img_gen_assignment.cogt_run_params.run_mode.is_dry:
        return dry_img_gen_image_contents(img_gen_assignment)
    generated_image_list = await img_gen_image_list(img_gen_assignment)
    image_contents: list[ImageContent] = []
    for raw_details in generated_image_list:
        image_content = await generated_content_factory.make_image_content(
            primary_id=img_gen_assignment.job_metadata.user_id,
            secondary_id=img_gen_assignment.job_metadata.pipeline_run_id,
            raw_details=raw_details,
        )
        image_content.source_prompt = img_gen_assignment.img_gen_prompt.positive_text
        image_content.source_negative_prompt = img_gen_assignment.img_gen_prompt.negative_text
        image_contents.append(image_content)
    return image_contents
