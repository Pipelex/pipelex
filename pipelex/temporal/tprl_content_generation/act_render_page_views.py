from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import RenderPageViewsAssignment
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.hub import get_storage_provider
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer


@activity.defn
@convert_pipelex_errors
async def act_render_page_views(render_assignment: RenderPageViewsAssignment) -> list[ImageContent]:
    """Render PDF pages as images, store them, and return lightweight ImageContent references.

    Performs pypdfium2 rendering and S3 storage within the activity so that
    large binary data never crosses a Temporal workflow boundary.
    """
    log.dev("act_render_page_views")
    page_view_images = await pypdfium2_renderer.render_pdf_pages_from_uri(
        pdf_uri=render_assignment.document_uri,
        dpi=render_assignment.page_views_dpi,
    )
    storage_provider = get_storage_provider()
    generated_content_factory = GeneratedContentFactory(storage_provider=storage_provider)
    image_contents: list[ImageContent] = []
    for page_view_image in page_view_images:
        raw_details = GeneratedImageRawDetails.make_from_pil_image(
            pil_image=page_view_image,
            image_format=ImageFormat.PNG,
        )
        image_content = await generated_content_factory.make_image_content(
            primary_id=render_assignment.job_metadata.user_id,
            secondary_id=render_assignment.job_metadata.pipeline_run_id,
            raw_details=raw_details,
        )
        image_contents.append(image_content)
    return image_contents
