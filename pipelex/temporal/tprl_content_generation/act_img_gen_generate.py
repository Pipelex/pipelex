from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import ImgGenAssignment
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.content_generation.img_gen_generate import img_gen_image_list_and_store, img_gen_single_image_and_store
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.hub import get_storage_provider
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors


@activity.defn
@convert_pipelex_errors
async def act_img_gen_images(img_gen_assignment: ImgGenAssignment) -> list[ImageContent]:
    """Generate images and store them, returning lightweight ImageContent references.

    Large binary data (base64/bytes) is stored within the activity and never crosses
    the Temporal workflow boundary — only URLs are returned.
    """
    log.dev("act_img_gen_images")
    storage_provider = get_storage_provider()
    generated_content_factory = GeneratedContentFactory(storage_provider=storage_provider)
    if img_gen_assignment.nb_images > 1:
        return await img_gen_image_list_and_store(
            img_gen_assignment=img_gen_assignment,
            generated_content_factory=generated_content_factory,
        )
    image_content = await img_gen_single_image_and_store(
        img_gen_assignment=img_gen_assignment,
        generated_content_factory=generated_content_factory,
    )
    return [image_content]
