from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import RenderPageViewsAssignment
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.content_generation.render_generate import render_page_views_and_store
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.hub import get_storage_provider
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors


@activity.defn
@convert_pipelex_errors
async def act_render_page_views(render_assignment: RenderPageViewsAssignment) -> list[ImageContent]:
    """Render PDF pages as images, store them, and return lightweight ImageContent references.

    Performs pypdfium2 rendering and storage within the activity so that large binary data
    never crosses a Temporal workflow boundary. The rendering + storing logic lives in the
    framework-agnostic ``render_page_views_and_store`` leaf, shared with the direct backend.
    """
    log.dev("act_render_page_views")
    storage_provider = get_storage_provider()
    generated_content_factory = GeneratedContentFactory(storage_provider=storage_provider)
    return await render_page_views_and_store(
        render_assignment=render_assignment,
        generated_content_factory=generated_content_factory,
    )
