from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from pipelex import log
from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.document.prompt_document_factory import PromptDocumentFactory
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory

if TYPE_CHECKING:
    from pipelex.cogt.image.prompt_image import PromptImage

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.hub import get_content_generator
from pipelex.pipe_operators.llm.document_reference import DocumentReference, DocumentReferenceKind
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
    user_image_references: list[ImageReference] | None = None
    user_document_references: list[DocumentReference] | None = None
    system_image_references: list[ImageReference] | None = None
    system_document_references: list[DocumentReference] | None = None

    def required_variables(self) -> set[str]:
        required_variables: set[str] = set()
        if self.user_image_references:
            image_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.user_image_references]
            required_variables.update(image_ref_root_names)
        if self.user_document_references:
            doc_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.user_document_references]
            required_variables.update(doc_ref_root_names)
        if self.system_image_references:
            system_image_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.system_image_references]
            required_variables.update(system_image_ref_root_names)
        if self.system_document_references:
            system_doc_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.system_document_references]
            required_variables.update(system_doc_ref_root_names)

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
        # Extract system prompt images FIRST, then user prompt images
        ############################################################
        image_registry = ImageRegistry()
        # Maps image variable name to its 0-based registry index (for placeholder generation)
        image_registry_indices: dict[str, int] = {}
        # Track which variable paths are lists, so we can substitute the whole list
        list_image_refs: list[ImageReference] = []

        # Process system prompt image references first (so they get lower numbers)
        if self.system_image_references:
            for image_ref in self.system_image_references:
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

        # Process user prompt image references (DIRECT and DIRECT_LIST kinds)
        if self.user_image_references:
            for image_ref in self.user_image_references:
                match image_ref.kind:
                    case ImageReferenceKind.DIRECT:
                        # Single ImageContent reference
                        self._extract_direct_image(
                            image_ref=image_ref,
                            context_provider=context_provider,
                            image_registry=image_registry,
                            image_registry_indices=image_registry_indices,
                        )
                    case ImageReferenceKind.DIRECT_LIST:
                        # List of ImageContent reference
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
        # Direct Document Extraction
        # Extract system prompt documents FIRST, then user prompt documents
        ############################################################
        prompt_user_documents: dict[str, PromptDocument] = {}
        list_document_refs: list[DocumentReference] = []

        # Process system prompt document references first (so they get lower numbers)
        if self.system_document_references:
            for doc_ref in self.system_document_references:
                match doc_ref.kind:
                    case DocumentReferenceKind.DIRECT:
                        self._extract_direct_document(
                            doc_ref=doc_ref,
                            context_provider=context_provider,
                            prompt_user_documents=prompt_user_documents,
                        )
                    case DocumentReferenceKind.DIRECT_LIST:
                        self._extract_direct_list_documents(
                            doc_ref=doc_ref,
                            context_provider=context_provider,
                            prompt_user_documents=prompt_user_documents,
                        )
                        list_document_refs.append(doc_ref)

        # Process user prompt document references
        if self.user_document_references:
            for doc_ref in self.user_document_references:
                match doc_ref.kind:
                    case DocumentReferenceKind.DIRECT:
                        self._extract_direct_document(
                            doc_ref=doc_ref,
                            context_provider=context_provider,
                            prompt_user_documents=prompt_user_documents,
                        )
                    case DocumentReferenceKind.DIRECT_LIST:
                        self._extract_direct_list_documents(
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
                # Skip dotted paths (e.g., "page.page_view") - handled by tag filter
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
        if self.system_prompt_blueprint:
            system_text = await self._unravel_text(
                context_provider=context_provider,
                jinja2_blueprint=self.system_prompt_blueprint,
                extra_params=extra_params,
                image_registry=image_registry,
            )

        ############################################################
        # User text (rendered AFTER system text for consistent image ordering)
        ############################################################
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
        self,
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
                raise LLMPromptBlueprintValueError(msg)
        except ContextProviderError as exc:
            msg = f"Could not find image '{image_ref.variable_path}' in context: {exc}"
            raise LLMPromptBlueprintValueError(msg) from exc

    def _extract_direct_list_images(
        self,
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
            if isinstance(prompt_image_content, list):
                prompt_image_content = cast("list[Any]", prompt_image_content)
                for list_position, image_item in enumerate(prompt_image_content, start=1):
                    if not isinstance(image_item, ImageContent):
                        msg = f"Item of '{image_ref.variable_path}' is of type '{type(image_item).__name__}', expected ImageContent"
                        raise LLMPromptBlueprintValueError(msg)
                    registry_index = image_registry.register_image(image_item)
                    # Use list position (1-based) for variable name, registry index for image number
                    image_item_name = f"{image_ref.variable_path}[{list_position}]"
                    image_registry_indices[image_item_name] = registry_index
            elif isinstance(prompt_image_content, tuple):
                content_tuple: tuple[Any, ...] = cast("tuple[Any, ...]", prompt_image_content)
                for list_position, image_item in enumerate(content_tuple, start=1):
                    if not isinstance(image_item, ImageContent):
                        msg = f"Item of '{image_ref.variable_path}' is of type '{type(image_item).__name__}', expected ImageContent"
                        raise LLMPromptBlueprintValueError(msg)
                    registry_index = image_registry.register_image(image_item)
                    image_item_name = f"{image_ref.variable_path}[{list_position}]"
                    image_registry_indices[image_item_name] = registry_index
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

    def _extract_direct_document(
        self,
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
                raise LLMPromptBlueprintValueError(msg)
        except ContextProviderError as exc:
            msg = f"Could not find document '{doc_ref.variable_path}' in context: {exc}"
            raise LLMPromptBlueprintValueError(msg) from exc

    def _extract_direct_list_documents(
        self,
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
            if isinstance(prompt_document_content, list):
                prompt_document_content = cast("list[Any]", prompt_document_content)
                for doc_index, doc_item in enumerate(prompt_document_content, start=1):
                    if not isinstance(doc_item, DocumentContent):
                        msg = f"Item of '{doc_ref.variable_path}' is of type '{type(doc_item).__name__}', expected DocumentContent"
                        raise LLMPromptBlueprintValueError(msg)
                    user_document = PromptDocumentFactory.make_prompt_document(
                        uri=doc_item.url,
                        mime_type=doc_item.mime_type,
                    )
                    user_document_item_name = f"{doc_ref.variable_path}[{doc_index}]"
                    prompt_user_documents[user_document_item_name] = user_document
            elif isinstance(prompt_document_content, tuple):
                content_tuple: tuple[Any, ...] = cast("tuple[Any, ...]", prompt_document_content)
                for doc_index, doc_item in enumerate(content_tuple, start=1):
                    if not isinstance(doc_item, DocumentContent):
                        msg = f"Item of '{doc_ref.variable_path}' is of type '{type(doc_item).__name__}', expected DocumentContent"
                        raise LLMPromptBlueprintValueError(msg)
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
                raise LLMPromptBlueprintValueError(msg)
        except ContextProviderError as exc:
            msg = f"Could not find document list '{doc_ref.variable_path}' in context: {exc}"
            raise LLMPromptBlueprintValueError(msg) from exc
