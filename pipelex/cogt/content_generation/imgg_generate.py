# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import List, Union

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import ImggAssignment
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.imgg.imgg_job_factory import ImggJobFactory
from pipelex.hub import get_async_imgg_worker


async def imgg_gen_single_image(imgg_assignment: ImggAssignment) -> GeneratedImage:
    imgg_worker = get_async_imgg_worker(imgg_handle=imgg_assignment.imgg_handle)
    imgg_job = ImggJobFactory.make_imgg_job_from_prompt(
        imgg_prompt=imgg_assignment.imgg_prompt,
        imgg_job_params=imgg_assignment.imgg_job_params,
        imgg_job_config=imgg_assignment.imgg_job_config,
    )
    generated_image = await imgg_worker.gen_image(imgg_job=imgg_job)
    log.verbose(f"generated_image:\n{generated_image}")
    return generated_image


async def imgg_gen_image_list(imgg_assignment: ImggAssignment) -> List[GeneratedImage]:
    imgg_worker = get_async_imgg_worker(imgg_handle=imgg_assignment.imgg_handle)
    imgg_job = ImggJobFactory.make_imgg_job_from_prompt(
        imgg_prompt=imgg_assignment.imgg_prompt,
        imgg_job_params=imgg_assignment.imgg_job_params,
        imgg_job_config=imgg_assignment.imgg_job_config,
    )
    generated_image_list = await imgg_worker.gen_image_list(
        imgg_job=imgg_job,
        nb_images=imgg_assignment.nb_images,
    )
    log.verbose(f"generated_image_list:\n{generated_image_list}")
    return generated_image_list


async def imgg_gen_image(imgg_assignment: ImggAssignment) -> Union[GeneratedImage, List[GeneratedImage]]:
    if imgg_assignment.nb_images > 1:
        return await imgg_gen_image_list(imgg_assignment)
    else:
        return await imgg_gen_single_image(imgg_assignment)
