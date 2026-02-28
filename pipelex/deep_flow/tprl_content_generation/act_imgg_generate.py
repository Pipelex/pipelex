from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import ImggAssignment
from pipelex.cogt.content_generation.imgg_generate import imgg_gen_image
from pipelex.cogt.image.generated_image import GeneratedImage


@activity.defn
async def act_imgg_gen_images(imgg_assignment: ImggAssignment) -> list[GeneratedImage]:
    """This activity is used to generate a single image or a list of images.
    In case of a single image, the activity returns a list containing the single image.
    """
    log.dev("act_imgg_gen_images")
    image_or_list = await imgg_gen_image(imgg_assignment=imgg_assignment)
    if isinstance(image_or_list, list):
        return image_or_list
    else:
        return [image_or_list]
