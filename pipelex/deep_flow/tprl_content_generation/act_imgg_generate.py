from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import ImgGenAssignment
from pipelex.cogt.content_generation.img_gen_generate import img_gen_gen_image
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails


@activity.defn
async def act_img_gen_gen_images(img_gen_assignment: ImgGenAssignment) -> list[GeneratedImageRawDetails]:
    """This activity is used to generate a single image or a list of images.
    In case of a single image, the activity returns a list containing the single image.
    """
    log.dev("act_img_gen_gen_images")
    image_or_list = await img_gen_gen_image(img_gen_assignment=img_gen_assignment)
    if isinstance(image_or_list, list):
        return image_or_list
    else:
        return [image_or_list]
