"""Assemble an `ImgGenPrompt` — the image counterpart of `llm_prompt_content.assemble_llm_prompt`.

`run_img_gen` takes a *ready* `ImgGenPrompt`, by deliberate analogy with `run_llm_text` taking a ready
`LlmPromptContent`. The analogy is only honest if the kernel also ships the constructor: without this
module a `RuntimeBoot`-only process could call every other operator op and not the image one, because
the sole builder lived in `pipe_operators/` — an interpreter-layer module the kernel may not import.
`kernel/prompt_references.py` already hosts `ImageReference`, under a docstring asserting the kernel
resolves them; this is where that becomes true.

What lives here is the part a caller must not have to re-derive: the image registry, the `[Image N]`
placeholder tokens, and the correspondence between them. The registry is the single source of truth
for ordering — tokens are numbered from registry indices and `input_images` is read back from the same
registry — because a token/`input_images` order mismatch silently mislabels which image the prompt is
talking about, and nothing downstream can detect it.

What deliberately stays with the caller is `max_prompt_images`. That limit is a property of the model
a caller has chosen, its breach raises an interpreter-layer error, and checking `len(input_images)` is
a line of code — not the kind of subtlety this module exists to centralise.
"""

from typing import TYPE_CHECKING, Any, cast

from pipelex import log
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.kernel.exceptions import PromptContentError
from pipelex.kernel.prompt_references import ImageReference, ImageReferenceKind
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract
from pipelex.tools.misc.dict_utils import substitute_nested_in_context
from pipelex.tools.misc.exceptions import ContextProviderError

if TYPE_CHECKING:
    from pipelex.cogt.image.prompt_image import PromptImage


async def assemble_img_gen_prompt(
    *,
    context_provider: ContextProviderAbstract,
    prompt_blueprint: TemplateBlueprint | None = None,
    negative_prompt_blueprint: TemplateBlueprint | None = None,
    image_references: list[ImageReference] | None = None,
    extra_params: dict[str, Any] | None = None,
) -> ImgGenPrompt:
    """Build an `ImgGenPrompt`: resolve image references, render the templates, collect the images.

    `context_provider` is typically the `WorkingMemory` the step runs against. Raises
    `PromptContentError` when an image reference names something the context does not hold, or holds
    as the wrong type.
    """
    image_registry = ImageRegistry()
    # Maps image variable name to its 0-based registry index (for placeholder generation)
    image_registry_indices: dict[str, int] = {}
    # Track which variable paths are lists, so we can substitute the whole list
    list_image_refs: list[ImageReference] = []

    if image_references:
        for image_ref in image_references:
            match image_ref.kind:
                case ImageReferenceKind.DIRECT:
                    _extract_direct_image(
                        image_ref=image_ref,
                        context_provider=context_provider,
                        image_registry=image_registry,
                        image_registry_indices=image_registry_indices,
                    )
                case ImageReferenceKind.DIRECT_LIST:
                    _extract_direct_list_images(
                        image_ref=image_ref,
                        context_provider=context_provider,
                        image_registry=image_registry,
                        image_registry_indices=image_registry_indices,
                    )
                    list_image_refs.append(image_ref)
                case ImageReferenceKind.NESTED:
                    # Nested images will be extracted by the | with_images filter
                    # during template rendering - the registry is passed in context
                    pass

    extra_params = _with_image_placeholders(
        extra_params=extra_params,
        image_registry_indices=image_registry_indices,
        list_image_refs=list_image_refs,
    )

    positive_text: str = ""
    if prompt_blueprint:
        positive_text = await _render_text(
            context_provider=context_provider,
            template_blueprint=prompt_blueprint,
            extra_params=extra_params,
            image_registry=image_registry,
        )

    negative_text: str | None = None
    if negative_prompt_blueprint:
        negative_text = await _render_text(
            context_provider=context_provider,
            template_blueprint=negative_prompt_blueprint,
            extra_params=extra_params,
            image_registry=image_registry,
        )

    # The registry contains all images (direct + nested) in the correct order, already deduplicated
    # by URL. This ensures [Image N] tokens match positions.
    input_images: list[PromptImage] | None = None
    if image_registry.images:
        input_images = [PromptImageFactory.make_prompt_image(uri=registry_image.url) for registry_image in image_registry.images]

    log.verbose(f"ImgGenPrompt: {len(input_images or [])} input images")

    return ImgGenPrompt(
        positive_text=positive_text,
        negative_text=negative_text,
        input_images=input_images,
    )


def _with_image_placeholders(
    *,
    extra_params: dict[str, Any] | None,
    image_registry_indices: dict[str, int],
    list_image_refs: list[ImageReference],
) -> dict[str, Any]:
    """Add the `[Image N]` tokens the templates substitute, numbered from the registry."""
    params = dict(extra_params) if extra_params else {}
    if not image_registry_indices:
        return params

    # Collect list variable paths for exclusion from direct substitution
    list_variable_paths = {list_ref.variable_path for list_ref in list_image_refs}

    for image_name, registry_index in image_registry_indices.items():
        # Skip list item references (e.g., "images[1]")
        if "[" in image_name:
            continue
        # Skip dotted paths (e.g., "page.page_view") - handled by finalize/filter at render time
        if "." in image_name:
            continue
        # Skip list variable references (handled separately below)
        if image_name in list_variable_paths:
            continue
        params[image_name] = f"[Image {registry_index + 1}]"

    # For list image references, substitute the list variable itself with a string containing all
    # the [Image N] tokens for items in that list
    for list_ref in list_image_refs:
        list_tokens: list[str] = []
        for image_name, registry_index in image_registry_indices.items():
            # Check if this image belongs to this list (e.g., "collection_a[1]" belongs to "collection_a")
            if image_name.startswith(f"{list_ref.variable_path}["):
                list_tokens.append(f"[Image {registry_index + 1}]")
        if list_tokens:
            params[list_ref.variable_path] = ", ".join(list_tokens)

    return params


def _extract_direct_image(
    *,
    image_ref: ImageReference,
    context_provider: ContextProviderAbstract,
    image_registry: ImageRegistry,
    image_registry_indices: dict[str, int],
) -> None:
    """Extract a single ImageContent from context and register it."""
    log.verbose(f"Getting direct image '{image_ref.variable_path}' from context")
    try:
        prompt_image_content = context_provider.get_typed_object_or_attribute(
            name=image_ref.variable_path,
            wanted_type=ImageContent,
            accept_list=False,
        )
        if isinstance(prompt_image_content, ImageContent):
            registry_index = image_registry.register_image(prompt_image_content)
            image_registry_indices[image_ref.variable_path] = registry_index
        else:
            msg = f"Image reference '{image_ref.variable_path}' is of type '{type(prompt_image_content).__name__}', expected ImageContent"
            raise PromptContentError(msg)
    except ContextProviderError as exc:
        msg = f"Could not find image '{image_ref.variable_path}' in context: {exc}"
        raise PromptContentError(msg) from exc


def _extract_direct_list_images(
    *,
    image_ref: ImageReference,
    context_provider: ContextProviderAbstract,
    image_registry: ImageRegistry,
    image_registry_indices: dict[str, int],
) -> None:
    """Extract a list of ImageContent from context and register them."""
    log.verbose(f"Getting image list '{image_ref.variable_path}' from context")
    try:
        prompt_image_content = context_provider.get_typed_object_or_attribute(
            name=image_ref.variable_path,
            wanted_type=ImageContent,
            accept_list=True,
        )
        if isinstance(prompt_image_content, (list, tuple)):
            items = cast("list[Any] | tuple[Any, ...]", prompt_image_content)
            for list_position, image_item in enumerate(items, start=1):
                if not isinstance(image_item, ImageContent):
                    msg = f"Item of '{image_ref.variable_path}' is of type '{type(image_item).__name__}', expected ImageContent"
                    raise PromptContentError(msg)
                registry_index = image_registry.register_image(image_item)
                # Use list position (1-based) for variable name, registry index for image number
                image_item_name = f"{image_ref.variable_path}[{list_position}]"
                image_registry_indices[image_item_name] = registry_index
        else:
            msg = (
                f"Image list reference '{image_ref.variable_path}' is of type '{type(prompt_image_content).__name__}', "
                "expected list or tuple of ImageContent"
            )
            raise PromptContentError(msg)
    except ContextProviderError as exc:
        msg = f"Could not find image list '{image_ref.variable_path}' in context: {exc}"
        raise PromptContentError(msg) from exc


async def _render_text(
    *,
    context_provider: ContextProviderAbstract,
    template_blueprint: TemplateBlueprint,
    extra_params: dict[str, Any] | None = None,
    image_registry: ImageRegistry | None = None,
) -> str:
    """Render a template with context and optional image registry."""
    context: dict[str, Any] = context_provider.generate_context()
    if extra_params:
        context = substitute_nested_in_context(context=context, extra_params=extra_params)
    if template_blueprint.extra_context:
        context.update(**template_blueprint.extra_context)

    # Add image registry to context for | with_images and | format filters
    if image_registry is not None:
        context[Jinja2ContextKey.IMAGE_REGISTRY] = image_registry

    finalize = image_registry.make_finalize() if image_registry and image_registry.images else None

    return await render_template(
        template=template_blueprint.template,
        category=template_blueprint.category,
        context=context,
        templating_style=template_blueprint.templating_style,
        finalize=finalize,
    )
