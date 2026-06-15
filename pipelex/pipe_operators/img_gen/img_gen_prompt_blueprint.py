"""Blueprint for building image generation prompts with image extraction support.

This module provides the ImgGenPromptBlueprint class which handles:
- Template rendering for positive/negative prompts
- Image reference extraction (direct, list, and nested)
- Placeholder generation for image references
"""

from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from pipelex import log
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.pipe_operators.img_gen.exceptions import PipeImgGenFactoryError
from pipelex.pipe_operators.shared.image_reference import ImageReference, ImageReferenceKind
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract
from pipelex.tools.misc.dict_utils import substitute_nested_in_context
from pipelex.tools.misc.exceptions import ContextProviderError
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

if TYPE_CHECKING:
    from pipelex.cogt.image.prompt_image import PromptImage


class ImgGenPromptBlueprintValueError(ValueError):
    """Raised when there's an issue extracting values for img_gen prompt blueprint."""


class ImgGenPromptBlueprint(BaseModel):
    """Blueprint for building ImgGenPrompt with optional image inputs.

    This class handles:
    - Template rendering for positive and negative prompts
    - Image reference extraction (direct images, image lists, nested images)
    - [Image N] placeholder generation in prompt text
    - Collecting all images for the ImgGenPrompt.input_images field
    """

    prompt_blueprint: TemplateBlueprint | None = None
    negative_prompt_blueprint: TemplateBlueprint | None = None
    image_references: list[ImageReference] | None = None

    def required_variables(self) -> set[str]:
        """Return the set of required variables from templates and image references."""
        required_variables: set[str] = set()

        if self.image_references:
            image_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.image_references]
            required_variables.update(image_ref_root_names)

        if self.prompt_blueprint:
            required_variables.update(get_root_from_dotted_path(path) for path in self.prompt_blueprint.required_variables())
        if self.negative_prompt_blueprint:
            required_variables.update(get_root_from_dotted_path(path) for path in self.negative_prompt_blueprint.required_variables())

        return {variable_name for variable_name in required_variables if not variable_name.startswith("_")}

    async def make_img_gen_prompt(
        self,
        *,
        context_provider: ContextProviderAbstract,
        extra_params: dict[str, Any] | None = None,
        max_prompt_images: int | None = None,
    ) -> ImgGenPrompt:
        """Build an ImgGenPrompt from the blueprint.

        Args:
            context_provider: Provider for variable values (typically WorkingMemory)
            extra_params: Additional parameters for template substitution
            max_prompt_images: Maximum number of images allowed (for validation)

        Returns:
            ImgGenPrompt with rendered text and extracted input images

        Raises:
            ImgGenPromptBlueprintValueError: If image extraction fails
            PipeImgGenFactoryError: If max_prompt_images is exceeded
        """
        ############################################################
        # Image Registry and Direct Image Extraction
        ############################################################
        image_registry = ImageRegistry()
        # Maps image variable name to its 0-based registry index (for placeholder generation)
        image_registry_indices: dict[str, int] = {}
        # Track which variable paths are lists, so we can substitute the whole list
        list_image_refs: list[ImageReference] = []

        # Process image references (DIRECT and DIRECT_LIST kinds)
        if self.image_references:
            for image_ref in self.image_references:
                match image_ref.kind:
                    case ImageReferenceKind.DIRECT:
                        self._extract_direct_image(
                            image_ref=image_ref,
                            context_provider=context_provider,
                            image_registry=image_registry,
                            image_registry_indices=image_registry_indices,
                        )
                    case ImageReferenceKind.DIRECT_LIST:
                        self._extract_direct_list_images(
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
        # Prepare extra_params with image placeholders
        ############################################################
        extra_params = dict(extra_params) if extra_params else {}
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

        ############################################################
        # Render prompt text
        ############################################################
        positive_text: str = ""
        if self.prompt_blueprint:
            positive_text = await self._render_text(
                context_provider=context_provider,
                template_blueprint=self.prompt_blueprint,
                extra_params=extra_params,
                image_registry=image_registry,
            )

        negative_text: str | None = None
        if self.negative_prompt_blueprint:
            negative_text = await self._render_text(
                context_provider=context_provider,
                template_blueprint=self.negative_prompt_blueprint,
                extra_params=extra_params,
                image_registry=image_registry,
            )

        ############################################################
        # Collect all images from registry (single source of truth)
        ############################################################
        # The registry contains all images (direct + nested) in the correct order,
        # already deduplicated by URL. This ensures [Image N] tokens match positions.
        input_images: list[PromptImage] | None = None
        if image_registry.images:
            input_images = [PromptImageFactory.make_prompt_image(uri=registry_image.url) for registry_image in image_registry.images]

            # Validate against max_prompt_images if specified
            if max_prompt_images is not None and len(input_images) > max_prompt_images:
                msg = (
                    f"Too many input images: got {len(input_images)}, but model only supports {max_prompt_images}. "
                    f"Reduce the number of images in your template."
                )
                raise PipeImgGenFactoryError(msg)

        log.verbose(f"ImgGenPrompt: {len(input_images or [])} input images")

        return ImgGenPrompt(
            positive_text=positive_text,
            negative_text=negative_text,
            input_images=input_images,
        )

    def _extract_direct_image(
        self,
        image_ref: ImageReference,
        *,
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
                raise ImgGenPromptBlueprintValueError(msg)
        except ContextProviderError as exc:
            msg = f"Could not find image '{image_ref.variable_path}' in context: {exc}"
            raise ImgGenPromptBlueprintValueError(msg) from exc

    def _extract_direct_list_images(
        self,
        image_ref: ImageReference,
        *,
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
            if isinstance(prompt_image_content, list):
                prompt_image_content = cast("list[Any]", prompt_image_content)
                for list_position, image_item in enumerate(prompt_image_content, start=1):
                    if not isinstance(image_item, ImageContent):
                        msg = f"Item of '{image_ref.variable_path}' is of type '{type(image_item).__name__}', expected ImageContent"
                        raise ImgGenPromptBlueprintValueError(msg)
                    registry_index = image_registry.register_image(image_item)
                    # Use list position (1-based) for variable name, registry index for image number
                    image_item_name = f"{image_ref.variable_path}[{list_position}]"
                    image_registry_indices[image_item_name] = registry_index
            elif isinstance(prompt_image_content, tuple):
                content_tuple: tuple[Any, ...] = cast("tuple[Any, ...]", prompt_image_content)
                for list_position, image_item in enumerate(content_tuple, start=1):
                    if not isinstance(image_item, ImageContent):
                        msg = f"Item of '{image_ref.variable_path}' is of type '{type(image_item).__name__}', expected ImageContent"
                        raise ImgGenPromptBlueprintValueError(msg)
                    registry_index = image_registry.register_image(image_item)
                    image_item_name = f"{image_ref.variable_path}[{list_position}]"
                    image_registry_indices[image_item_name] = registry_index
            else:
                msg = (
                    f"Image list reference '{image_ref.variable_path}' is of type '{type(prompt_image_content).__name__}', "
                    "expected list or tuple of ImageContent"
                )
                raise ImgGenPromptBlueprintValueError(msg)
        except ContextProviderError as exc:
            msg = f"Could not find image list '{image_ref.variable_path}' in context: {exc}"
            raise ImgGenPromptBlueprintValueError(msg) from exc

    async def _render_text(
        self,
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
