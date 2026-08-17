"""Prompt assembly: templates plus memory-borne images and documents, into one `LLMPrompt`.

This is the kernel-layer home of what `LLMPromptBlueprint.make_llm_prompt` used to do inline.
`LLMPromptBlueprint` stays where it is — it is a language artifact, what `.mthds` parses into, and it
keeps its parse-and-validate role — but it now maps down onto :func:`assemble_llm_prompt` rather than
holding the semantics, so the interpreter and a programmatic caller assemble prompts through the
same code.

The ordering here is load-bearing and is preserved exactly: system-prompt images are registered
before user-prompt ones, and the system text renders before the user text, so the `[Image N]` tokens
a template interpolates match the positions of the images handed to the model.
"""

from typing import TYPE_CHECKING, Any, Self, cast

from pydantic import BaseModel

from pipelex import log
from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.document.prompt_document_factory import PromptDocumentFactory
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.kernel.exceptions import PromptContentError
from pipelex.kernel.prompt_references import DocumentReference, DocumentReferenceKind, ImageReference, ImageReferenceKind
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract
from pipelex.tools.misc.dict_utils import substitute_nested_in_context
from pipelex.tools.misc.exceptions import ContextProviderError
from pipelex.tools.templating.templating_style import TemplatingStyle

if TYPE_CHECKING:
    from pipelex.cogt.image.prompt_image import PromptImage


class LlmPromptContent(BaseModel):
    """What a prompt is made of, before anything is rendered: two templates and their references.

    The reference lists are how images and documents enter a prompt — the templates interpolate
    `[Image N]` / `[Document N]` tokens, and the referenced content is fetched out of the context
    provider (working memory) at assembly time.
    """

    user_template: TemplateBlueprint | None = None
    system_template: TemplateBlueprint | None = None
    user_image_references: list[ImageReference] | None = None
    user_document_references: list[DocumentReference] | None = None
    system_image_references: list[ImageReference] | None = None
    system_document_references: list[DocumentReference] | None = None

    @classmethod
    def make_from_text(cls, *, user: str, system: str | None = None) -> Self:
        """Text-only prompt content from two template strings, rendered against the caller's memory.

        No image or document references: a caller that needs those builds the model directly, which
        is what the interpreter's blueprint mapping does.
        """
        return cls(
            user_template=TemplateBlueprint(template=user, category=TemplateCategory.LLM_PROMPT),
            system_template=TemplateBlueprint(template=system, category=TemplateCategory.LLM_PROMPT) if system is not None else None,
        )


async def assemble_llm_prompt(
    *,
    prompt_content: LlmPromptContent,
    context_provider: ContextProviderAbstract,
    output_structure_prompt: str | None = None,
    extra_params: dict[str, Any] | None = None,
    templating_style: TemplatingStyle,
) -> LLMPrompt:
    """Render both templates against the context and collect the images and documents they reference."""
    ############################################################
    # Image Registry and Direct Image Extraction
    # Extract system prompt images FIRST, then user prompt images
    ############################################################
    image_registry = ImageRegistry()
    # Maps image variable name to its 0-based registry index (for placeholder generation)
    image_registry_indices: dict[str, int] = {}
    # Track which variable paths are lists, so we can substitute the whole list
    list_image_refs: list[ImageReference] = []

    # Process system prompt image references first (so they get lower numbers), then the user ones.
    for image_references in (prompt_content.system_image_references, prompt_content.user_image_references):
        if not image_references:
            continue
        for image_ref in image_references:
            match image_ref.kind:
                case ImageReferenceKind.DIRECT:
                    # Single ImageContent reference
                    _extract_direct_image(
                        image_ref=image_ref,
                        context_provider=context_provider,
                        image_registry=image_registry,
                        image_registry_indices=image_registry_indices,
                    )
                case ImageReferenceKind.DIRECT_LIST:
                    # List of ImageContent reference
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

    ############################################################
    # Direct Document Extraction
    # Extract system prompt documents FIRST, then user prompt documents
    ############################################################
    prompt_user_documents: dict[str, PromptDocument] = {}
    list_document_refs: list[DocumentReference] = []

    for document_references in (prompt_content.system_document_references, prompt_content.user_document_references):
        if not document_references:
            continue
        for doc_ref in document_references:
            match doc_ref.kind:
                case DocumentReferenceKind.DIRECT:
                    _extract_direct_document(
                        doc_ref=doc_ref,
                        context_provider=context_provider,
                        prompt_user_documents=prompt_user_documents,
                    )
                case DocumentReferenceKind.DIRECT_LIST:
                    _extract_direct_list_documents(
                        doc_ref=doc_ref,
                        context_provider=context_provider,
                        prompt_user_documents=prompt_user_documents,
                    )
                    list_document_refs.append(doc_ref)

    ############################################################
    # User text
    ############################################################
    # Add image placeholders to extra_params for substitution in template
    # - Direct images (non-dotted paths like "image"): add placeholder directly
    # - List images: add list variable with all tokens joined
    # - Dotted paths (e.g., "page.page_view"): handled by tag filter via ImageRegistry.get_image_placeholder()
    #   because dotted paths cannot be substituted in immutable StuffArtefacts
    extra_params = extra_params or {}
    if image_registry_indices:
        # Collect list variable paths for exclusion from direct substitution
        list_variable_paths = {list_ref.variable_path for list_ref in list_image_refs}

        # Add placeholders for direct (non-dotted, non-list) images
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
            # Add direct image placeholder
            extra_params[image_name] = f"[Image {registry_index + 1}]"

        # For list image references, substitute the list variable itself
        # with a string containing all the [Image N] tokens for items in that list
        for list_ref in list_image_refs:
            list_tokens: list[str] = []
            for image_name, registry_index in image_registry_indices.items():
                # Check if this image belongs to this list (e.g., "collection_a[1]" belongs to "collection_a")
                if image_name.startswith(f"{list_ref.variable_path}["):
                    list_tokens.append(f"[Image {registry_index + 1}]")
            if list_tokens:
                extra_params[list_ref.variable_path] = ", ".join(list_tokens)

    # Replace direct document variables with numbered tags
    if prompt_user_documents:
        document_names = list(prompt_user_documents.keys())
        for document_index, document_name in enumerate(document_names):
            extra_params[document_name] = f"[Document {document_index + 1}]"

        # For list document references, also substitute the list variable itself
        for doc_list_ref in list_document_refs:
            doc_list_tokens: list[str] = []
            for document_name in document_names:
                if document_name.startswith(f"{doc_list_ref.variable_path}["):
                    doc_list_tokens.append(extra_params[document_name])
            if doc_list_tokens:
                extra_params[doc_list_ref.variable_path] = "\n".join(doc_list_tokens)

    ############################################################
    # System text (rendered FIRST so nested images get lower numbers)
    ############################################################
    system_text: str | None = None
    if prompt_content.system_template:
        system_text = await _unravel_text(
            context_provider=context_provider,
            jinja2_blueprint=prompt_content.system_template,
            extra_params=extra_params,
            image_registry=image_registry,
            templating_style=templating_style,
        )

    ############################################################
    # User text (rendered AFTER system text for consistent image ordering)
    ############################################################
    user_text: str | None = None
    if prompt_content.user_template:
        user_text = await _unravel_text(
            context_provider=context_provider,
            jinja2_blueprint=prompt_content.user_template,
            extra_params=extra_params,
            image_registry=image_registry,
            templating_style=templating_style,
        )
        if output_structure_prompt:
            user_text += output_structure_prompt
    else:
        user_text = output_structure_prompt
        # Note that output_structure_prompt can be None
        # it's OK to have a null user_text

    ############################################################
    # Collect all images from registry (single source of truth)
    ############################################################
    # The registry contains all images (direct + nested) in the correct order,
    # already deduplicated by URL. This ensures [Image N] tokens match positions.
    all_images: list[PromptImage] = [PromptImageFactory.make_prompt_image(uri=registry_image.url) for registry_image in image_registry.images]

    ############################################################
    # Collect all documents
    ############################################################
    all_documents: list[PromptDocument] = list(prompt_user_documents.values())

    ############################################################
    # Full LLMPrompt
    ############################################################
    return LLMPrompt(
        system_text=system_text,
        user_text=user_text,
        user_images=all_images,
        user_documents=all_documents,
    )


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
            image_items = cast("list[Any] | tuple[Any, ...]", prompt_image_content)
            for list_position, image_item in enumerate(image_items, start=1):
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


def _extract_direct_document(
    *,
    doc_ref: DocumentReference,
    context_provider: ContextProviderAbstract,
    prompt_user_documents: dict[str, PromptDocument],
) -> None:
    """Extract a single DocumentContent from context."""
    log.verbose(f"Getting direct document '{doc_ref.variable_path}' from context")
    try:
        prompt_document_content = context_provider.get_typed_object_or_attribute(
            name=doc_ref.variable_path,
            wanted_type=DocumentContent,
            accept_list=False,
        )
        if isinstance(prompt_document_content, DocumentContent):
            user_document = PromptDocumentFactory.make_prompt_document(
                uri=prompt_document_content.url,
                mime_type=prompt_document_content.mime_type,
            )
            prompt_user_documents[doc_ref.variable_path] = user_document
        else:
            msg = f"Document reference '{doc_ref.variable_path}' is of type '{type(prompt_document_content).__name__}', expected DocumentContent"
            raise PromptContentError(msg)
    except ContextProviderError as exc:
        msg = f"Could not find document '{doc_ref.variable_path}' in context: {exc}"
        raise PromptContentError(msg) from exc


def _extract_direct_list_documents(
    *,
    doc_ref: DocumentReference,
    context_provider: ContextProviderAbstract,
    prompt_user_documents: dict[str, PromptDocument],
) -> None:
    """Extract a list of DocumentContent from context."""
    log.verbose(f"Getting document list '{doc_ref.variable_path}' from context")
    try:
        prompt_document_content = context_provider.get_typed_object_or_attribute(
            name=doc_ref.variable_path,
            wanted_type=DocumentContent,
            accept_list=True,
        )
        if isinstance(prompt_document_content, (list, tuple)):
            document_items = cast("list[Any] | tuple[Any, ...]", prompt_document_content)
            for doc_index, doc_item in enumerate(document_items, start=1):
                if not isinstance(doc_item, DocumentContent):
                    msg = f"Item of '{doc_ref.variable_path}' is of type '{type(doc_item).__name__}', expected DocumentContent"
                    raise PromptContentError(msg)
                user_document = PromptDocumentFactory.make_prompt_document(
                    uri=doc_item.url,
                    mime_type=doc_item.mime_type,
                )
                user_document_item_name = f"{doc_ref.variable_path}[{doc_index}]"
                prompt_user_documents[user_document_item_name] = user_document
        else:
            msg = (
                f"Document list reference '{doc_ref.variable_path}' is of type '{type(prompt_document_content).__name__}', "
                "expected list or tuple of DocumentContent"
            )
            raise PromptContentError(msg)
    except ContextProviderError as exc:
        msg = f"Could not find document list '{doc_ref.variable_path}' in context: {exc}"
        raise PromptContentError(msg) from exc


async def _unravel_text(
    *,
    context_provider: ContextProviderAbstract,
    jinja2_blueprint: TemplateBlueprint,
    extra_params: dict[str, Any] | None = None,
    image_registry: ImageRegistry | None = None,
    templating_style: TemplatingStyle,
) -> str:
    # A style declared on the blueprint wins over the run-derived one. Kept as a local: writing
    # it onto `jinja2_blueprint` would mutate an object the pipe library holds and hands out.
    effective_style = jinja2_blueprint.templating_style or templating_style
    log.verbose(f"Rendering with prompting style {effective_style}")

    context: dict[str, Any] = context_provider.generate_context()
    if extra_params:
        context = substitute_nested_in_context(context=context, extra_params=extra_params)
    if jinja2_blueprint.extra_context:
        context.update(**jinja2_blueprint.extra_context)

    # Add image registry to context for | with_images and | format filters
    if image_registry is not None:
        context[Jinja2ContextKey.IMAGE_REGISTRY] = image_registry

    finalize = image_registry.make_finalize() if image_registry and image_registry.images else None

    return await render_template(
        template=jinja2_blueprint.template,
        category=jinja2_blueprint.category,
        context=context,
        templating_style=effective_style,
        finalize=finalize,
    )
