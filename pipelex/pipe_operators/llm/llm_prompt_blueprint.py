from typing import Any, cast

from pydantic import BaseModel

from pipelex import log
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.hub import get_content_generator
from pipelex.pipe_operators.llm.exceptions import LLMPromptBlueprintValueError
from pipelex.pipe_operators.llm.image_reference import ImageReference, ImageReferenceKind
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract, ContextProviderError
from pipelex.tools.misc.dict_utils import substitute_nested_in_context
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class LLMPromptBlueprint(BaseModel):
    templating_style: TemplatingStyle | None = None
    system_prompt_blueprint: TemplateBlueprint | None = None
    prompt_blueprint: TemplateBlueprint | None = None
    image_references: list[ImageReference] | None = None

    def required_variables(self) -> set[str]:
        required_variables: set[str] = set()
        if self.image_references:
            image_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.image_references]
            required_variables.update(image_ref_root_names)

        if self.prompt_blueprint:
            required_variables.update(self.prompt_blueprint.required_variables())
        if self.system_prompt_blueprint:
            required_variables.update(self.system_prompt_blueprint.required_variables())
        return {
            variable_name
            for variable_name in required_variables
            if not variable_name.startswith("_") and variable_name not in {"preliminary_text", "place_holder"}
        }

    # TODO: make this consistent with `LLMPromptFactoryAbstract` or `LLMPromptTemplate`,
    # let's get back to it when we have a better solution for structuring_method
    async def make_llm_prompt(
        self,
        output_concept_ref: str,
        context_provider: ContextProviderAbstract,
        output_structure_prompt: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> LLMPrompt:
        ############################################################
        # Image Registry and Direct Image Extraction
        ############################################################
        image_registry = ImageRegistry()
        prompt_user_images: dict[str, PromptImage] = {}
        # Track which variable paths are lists, so we can substitute the whole list
        list_image_refs: list[ImageReference] = []

        # Process direct image references (DIRECT and DIRECT_LIST kinds)
        if self.image_references:
            for image_ref in self.image_references:
                match image_ref.kind:
                    case ImageReferenceKind.DIRECT:
                        # Single ImageContent reference
                        self._extract_direct_image(
                            image_ref=image_ref,
                            context_provider=context_provider,
                            image_registry=image_registry,
                            prompt_user_images=prompt_user_images,
                        )
                    case ImageReferenceKind.DIRECT_LIST:
                        # List of ImageContent reference
                        self._extract_direct_list_images(
                            image_ref=image_ref,
                            context_provider=context_provider,
                            image_registry=image_registry,
                            prompt_user_images=prompt_user_images,
                        )
                        list_image_refs.append(image_ref)
                    case ImageReferenceKind.NESTED:
                        # Nested images will be extracted by the | with_images filter
                        # during template rendering - the registry is passed in context
                        pass

        ############################################################
        # User text
        ############################################################
        # Replace direct image variables with numbered tags
        extra_params = extra_params or {}
        if prompt_user_images:
            image_names = list(prompt_user_images.keys())
            for image_index, image_name in enumerate(image_names):
                extra_params[image_name] = f"[Image {image_index + 1}]"

            # For list image references, also substitute the list variable itself
            # with a string containing all the [Image N] tokens for items in that list
            for list_ref in list_image_refs:
                list_tokens: list[str] = []
                for image_name in image_names:
                    # Check if this image belongs to this list (e.g., "collection_a[1]" belongs to "collection_a")
                    if image_name.startswith(f"{list_ref.variable_path}["):
                        list_tokens.append(extra_params[image_name])
                if list_tokens:
                    extra_params[list_ref.variable_path] = "\n".join(list_tokens)

        user_text: str | None = None
        if self.prompt_blueprint:
            user_text = await self._unravel_text(
                context_provider=context_provider,
                jinja2_blueprint=self.prompt_blueprint,
                extra_params=extra_params,
                image_registry=image_registry,
            )
            if output_structure_prompt:
                user_text += output_structure_prompt
        else:
            user_text = output_structure_prompt
            # Note that output_structure_prompt can be None
            # it's OK to have a null user_text

        log.verbose(f"User text with {output_concept_ref=}:\n {user_text}")

        ############################################################
        # System text
        ############################################################
        system_text: str | None = None
        if self.system_prompt_blueprint:
            system_text = await self._unravel_text(
                context_provider=context_provider,
                jinja2_blueprint=self.system_prompt_blueprint,
                extra_params=extra_params,
                image_registry=image_registry,
            )

        ############################################################
        # Collect all images (direct + nested from registry)
        ############################################################
        # Get any additional images registered by the | with_images filter
        all_images: list[PromptImage] = list(prompt_user_images.values())
        for registry_image in image_registry.images:
            # Only add if not already in prompt_user_images (avoid duplicates)
            prompt_image = PromptImageFactory.make_prompt_image(uri=registry_image.url)
            if prompt_image not in all_images:
                all_images.append(prompt_image)

        ############################################################
        # Full LLMPrompt
        ############################################################
        return LLMPrompt(
            system_text=system_text,
            user_text=user_text,
            user_images=all_images,
        )

    def _extract_direct_image(
        self,
        image_ref: ImageReference,
        context_provider: ContextProviderAbstract,
        image_registry: ImageRegistry,
        prompt_user_images: dict[str, PromptImage],
    ) -> None:
        """Extract a single ImageContent from context."""
        log.verbose(f"Getting direct image '{image_ref.variable_path}' from context")
        try:
            prompt_image_content = context_provider.get_typed_object_or_attribute(
                name=image_ref.variable_path,
                wanted_type=ImageContent,
                accept_list=False,
            )
            if isinstance(prompt_image_content, ImageContent):
                image_registry.register_image(prompt_image_content)
                user_image = PromptImageFactory.make_prompt_image(uri=prompt_image_content.url)
                prompt_user_images[image_ref.variable_path] = user_image
            else:
                msg = f"Image reference '{image_ref.variable_path}' is of type '{type(prompt_image_content).__name__}', expected ImageContent"
                raise LLMPromptBlueprintValueError(msg)
        except ContextProviderError as exc:
            msg = f"Could not find image '{image_ref.variable_path}' in context: {exc}"
            raise LLMPromptBlueprintValueError(msg) from exc

    def _extract_direct_list_images(
        self,
        image_ref: ImageReference,
        context_provider: ContextProviderAbstract,
        image_registry: ImageRegistry,
        prompt_user_images: dict[str, PromptImage],
    ) -> None:
        """Extract a list of ImageContent from context."""
        log.verbose(f"Getting image list '{image_ref.variable_path}' from context")
        try:
            prompt_image_content = context_provider.get_typed_object_or_attribute(
                name=image_ref.variable_path,
                wanted_type=ImageContent,
                accept_list=True,
            )
            if isinstance(prompt_image_content, list):
                prompt_image_content = cast("list[ImageContent]", prompt_image_content)
                for image_index, image_item in enumerate(prompt_image_content, start=1):
                    if not isinstance(image_item, ImageContent):  # pyright: ignore[reportUnnecessaryIsInstance]
                        msg = f"Item of '{image_ref.variable_path}' is of type '{type(image_item).__name__}', expected ImageContent"
                        raise LLMPromptBlueprintValueError(msg)
                    image_registry.register_image(image_item)
                    user_image = PromptImageFactory.make_prompt_image(uri=image_item.url)
                    user_image_item_name = f"{image_ref.variable_path}[{image_index}]"
                    prompt_user_images[user_image_item_name] = user_image
            elif isinstance(prompt_image_content, tuple):
                content_tuple: tuple[ImageContent, ...] = cast("tuple[ImageContent, ...]", prompt_image_content)
                for image_index, image_item in enumerate(content_tuple, start=1):
                    image_registry.register_image(image_item)
                    user_image = PromptImageFactory.make_prompt_image(uri=image_item.url)
                    user_image_item_name = f"{image_ref.variable_path}[{image_index}]"
                    prompt_user_images[user_image_item_name] = user_image
            else:
                msg = (
                    f"Image list reference '{image_ref.variable_path}' is of type '{type(prompt_image_content).__name__}', "
                    "expected list or tuple of ImageContent"
                )
                raise LLMPromptBlueprintValueError(msg)
        except ContextProviderError as exc:
            msg = f"Could not find image list '{image_ref.variable_path}' in context: {exc}"
            raise LLMPromptBlueprintValueError(msg) from exc

    async def _unravel_text(
        self,
        context_provider: ContextProviderAbstract,
        jinja2_blueprint: TemplateBlueprint,
        extra_params: dict[str, Any] | None = None,
        image_registry: ImageRegistry | None = None,
    ) -> str:
        if (templating_style := self.templating_style) and not jinja2_blueprint.templating_style:
            jinja2_blueprint.templating_style = templating_style
            log.verbose(f"Setting prompting style to {templating_style}")

        context: dict[str, Any] = context_provider.generate_context()
        if extra_params:
            context = substitute_nested_in_context(context=context, extra_params=extra_params)
        if jinja2_blueprint.extra_context:
            context.update(**jinja2_blueprint.extra_context)

        # Add image registry to context for | with_images filter
        if image_registry is not None:
            context[Jinja2ContextKey.IMAGE_REGISTRY] = image_registry

        return await get_content_generator().make_templated_text(
            context=context,
            template=jinja2_blueprint.template,
            templating_style=self.templating_style,
            template_category=jinja2_blueprint.category,
        )
