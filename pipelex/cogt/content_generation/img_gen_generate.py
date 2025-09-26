from pipelex import log
from pipelex.cogt.content_generation.assignment_models import ImgGenAssignment
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_job_factory import ImgGenJobFactory
from pipelex.hub import get_img_gen_worker


async def img_gen_single_image(img_gen_assignment: ImgGenAssignment) -> GeneratedImage:
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


async def img_gen_image_list(img_gen_assignment: ImgGenAssignment) -> list[GeneratedImage]:
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


async def img_gen_image(img_gen_assignment: ImgGenAssignment) -> GeneratedImage | list[GeneratedImage]:
    if img_gen_assignment.nb_images > 1:
        return await img_gen_image_list(img_gen_assignment)
    return await img_gen_single_image(img_gen_assignment)
