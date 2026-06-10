"""Framework-agnostic page-view rendering leaf, sibling of ``img_gen_generate``.

Single home for "render a PDF's pages as images and store them": the direct
``ContentGenerator`` calls it inline; the Temporal ``act_render_page_views`` activity calls it
on a worker. Rendering and storage happen inside the leaf so large binary data never crosses a
Temporal workflow boundary — only URL-bearing ``ImageContent`` references are returned.
"""

from pipelex.cogt.content_generation.assignment_models import RenderPageViewsAssignment
from pipelex.cogt.content_generation.dry_mock import dry_render_page_views
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.tools.misc.image_utils import ImageFormat


async def render_page_views_and_store(
    render_assignment: RenderPageViewsAssignment,
    generated_content_factory: GeneratedContentFactory,
) -> list[ImageContent]:
    """Render PDF pages as images, store them, and return lightweight ImageContent references.

    The DRY branch sits here, above both the pypdfium2 rendering and the store step, so a dry run
    performs no rendering and no storage IO (eng review D10).
    """
    if render_assignment.cogt_run_params.run_mode.is_dry:
        return dry_render_page_views(render_assignment)
    # Deferred import: avoid pulling the pdf rendering SDK at module-load time
    from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer  # noqa: PLC0415

    page_view_images = await pypdfium2_renderer.render_pdf_pages_from_uri(
        pdf_uri=render_assignment.document_uri,
        dpi=render_assignment.page_views_dpi,
    )
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
