"""The user-prompt assembly every prompt-shaped operator shares: PipeLLM, PipeImgGen and PipeJudge.

A prompt template reads images and documents out of working memory through the references its
operator's factory resolved when the method loaded. Assembling the prompt means fetching each file a
reference names, numbering it, putting its numbered token where the template reads it, rendering the
template, and handing the model the files in the order their tokens number them. Three operators do
exactly this, so it is done here once: a second copy of the numbering would be free to drift from the
first, and a token that names a different file than the one handed over in its position mislabels the
prompt with nothing downstream able to notice.

**The registry is the single source of truth for the order.** Image tokens are numbered from
`ImageRegistry` indices and the image list is read back from the same registry, which also
deduplicates by URL. Documents are numbered in the order their references are registered.

**Several templates of one prompt share one `PromptFiles`**, so their tokens number one sequence: a
PipeLLM's system and user prompts, a PipeImgGen's positive and negative prompts. The ordering is
load-bearing. Every template's references are registered before any template renders, in the order
the caller lists them, and the templates render in that same order, so the nested images a
`with_images` filter registers while rendering come after every direct one.

**References come in three shapes.** A direct reference names one file (`photo`), a list reference
names a list of them (`album`, whose token is every item's token joined), and a dotted reference
reaches a file through a structure (`page.page_view`). A direct or list image is substituted as a
template parameter; a dotted image cannot be, since it lives inside an immutable artefact, so the
registry's `finalize` hook turns it into its token as Jinja2 prints it. A document is always
substituted as a parameter, a dotted path included.
"""

from collections.abc import Sequence
from typing import Any, Self, cast

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.document.prompt_document_factory import PromptDocumentFactory
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.kernel.exceptions import PromptContentError
from pipelex.kernel.prompt_references import DocumentReference, DocumentReferenceKind, ImageReference, ImageReferenceKind
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract
from pipelex.tools.misc.dict_utils import substitute_nested_in_context
from pipelex.tools.misc.exceptions import ContextProviderError
from pipelex.tools.templating.templating_style import TemplatingStyle


class UserPromptContent(BaseModel):
    """One prompt template and the image and document references its operator's factory resolved for it."""

    template: TemplateBlueprint
    image_references: list[ImageReference] | None = None
    document_references: list[DocumentReference] | None = None


class AssembledUserPrompt(BaseModel):
    """A rendered prompt and the files it presents, each list in the order its tokens number it."""

    model_config = ConfigDict(frozen=True)

    text: str
    images: list[PromptImage]
    documents: list[PromptDocument]


async def assemble_user_prompt(
    *,
    prompt_content: UserPromptContent,
    context_provider: ContextProviderAbstract,
    templating_style: TemplatingStyle,
    extra_params: dict[str, Any] | None = None,
) -> AssembledUserPrompt:
    """Resolve one template's references, number them, render it, and collect its files in token order.

    Raises:
        PromptContentError: when a reference names something the context does not hold, or holds as
            the wrong type.
    """
    prompt_files = PromptFiles.make_from_references(
        context_provider=context_provider,
        image_references=prompt_content.image_references or [],
        document_references=prompt_content.document_references or [],
    )
    text = await prompt_files.render(
        template_blueprint=prompt_content.template,
        context_provider=context_provider,
        extra_params=prompt_files.template_params(extra_params=extra_params),
        templating_style=templating_style,
    )
    return AssembledUserPrompt(text=text, images=prompt_files.prompt_images(), documents=prompt_files.prompt_documents())


class PromptFiles:
    """The images and documents one prompt's templates reference, numbered once for all of them.

    Built from every template's references at once, then asked for the parameters the templates
    substitute and used to render each template in turn. Read the files back only after the last
    template rendered, since rendering registers the images a `with_images` filter reaches.
    """

    def __init__(self) -> None:
        self._image_registry = ImageRegistry()
        # Each directly referenced image's 0-based registry index, keyed by its variable path, a list's
        # items keyed `album[1]`, `album[2]`, so the placeholders are numbered from the registry.
        self._image_registry_indices: dict[str, int] = {}
        self._list_image_paths: list[str] = []
        # Each referenced document keyed by its variable path, a list's items keyed `annexes[1]`, in the
        # order their references were registered, which is the order their tokens number them.
        self._documents: dict[str, PromptDocument] = {}
        self._list_document_paths: list[str] = []

    @classmethod
    def make_from_references(
        cls,
        *,
        context_provider: ContextProviderAbstract,
        image_references: Sequence[ImageReference],
        document_references: Sequence[DocumentReference],
    ) -> Self:
        """Fetch every referenced file out of the context and register it, in the order given.

        Raises:
            PromptContentError: when a reference names something the context does not hold, or holds
                as the wrong type.
        """
        prompt_files = cls()
        for image_reference in image_references:
            match image_reference.kind:
                case ImageReferenceKind.DIRECT:
                    prompt_files._register_direct_image(image_reference=image_reference, context_provider=context_provider)
                case ImageReferenceKind.DIRECT_LIST:
                    prompt_files._register_direct_list_images(image_reference=image_reference, context_provider=context_provider)
                    prompt_files._list_image_paths.append(image_reference.variable_path)
                case ImageReferenceKind.NESTED:
                    # Registered while rendering, by the `with_images` filter, which reads the registry
                    # from the context.
                    pass
        for document_reference in document_references:
            match document_reference.kind:
                case DocumentReferenceKind.DIRECT:
                    prompt_files._register_direct_document(document_reference=document_reference, context_provider=context_provider)
                case DocumentReferenceKind.DIRECT_LIST:
                    prompt_files._register_direct_list_documents(document_reference=document_reference, context_provider=context_provider)
                    prompt_files._list_document_paths.append(document_reference.variable_path)
        return prompt_files

    def template_params(self, *, extra_params: dict[str, Any] | None) -> dict[str, Any]:
        """The caller's parameters, plus the token each direct, list and dotted-document reference renders as.

        The caller's dict is copied, never written to. A dotted image path gets no parameter: its
        token comes from the registry's `finalize` hook as the template prints it.
        """
        params = dict(extra_params) if extra_params else {}
        for image_path, registry_index in self._image_registry_indices.items():
            # A list's items are rendered through the list's own parameter below, a dotted path through finalize.
            if "[" in image_path or "." in image_path or image_path in self._list_image_paths:
                continue
            params[image_path] = _image_token(registry_index=registry_index)
        for list_path in self._list_image_paths:
            list_tokens = [
                _image_token(registry_index=registry_index)
                for image_path, registry_index in self._image_registry_indices.items()
                if image_path.startswith(f"{list_path}[")
            ]
            if list_tokens:
                params[list_path] = ", ".join(list_tokens)

        document_paths = list(self._documents)
        for document_index, document_path in enumerate(document_paths, start=1):
            params[document_path] = f"[Document {document_index}]"
        for list_path in self._list_document_paths:
            list_tokens = [params[document_path] for document_path in document_paths if document_path.startswith(f"{list_path}[")]
            if list_tokens:
                params[list_path] = "\n".join(list_tokens)
        return params

    async def render(
        self,
        *,
        template_blueprint: TemplateBlueprint,
        context_provider: ContextProviderAbstract,
        extra_params: dict[str, Any],
        templating_style: TemplatingStyle,
    ) -> str:
        """Render one template against the context, its references substituted by `extra_params`.

        A style declared on the blueprint wins over the resolved one, and is kept as a local: writing it
        onto the blueprint would mutate an object the pipe library holds and hands out.
        """
        effective_style = template_blueprint.templating_style or templating_style

        context: dict[str, Any] = context_provider.generate_context()
        if extra_params:
            context = substitute_nested_in_context(context=context, extra_params=extra_params)
        if template_blueprint.extra_context:
            context.update(**template_blueprint.extra_context)
        # The registry rides in the context for the `with_images` and `format` filters.
        context[Jinja2ContextKey.IMAGE_REGISTRY] = self._image_registry

        finalize = self._image_registry.make_finalize() if self._image_registry.images else None

        return await render_template(
            template=template_blueprint.template,
            category=template_blueprint.category,
            context=context,
            templating_style=effective_style,
            finalize=finalize,
        )

    def prompt_images(self) -> list[PromptImage]:
        """Every registered image in registry order, each keeping the format its preparation established.

        Carrying the MIME type lets the worker check the format instead of guessing it again.
        """
        return [PromptImageFactory.make_prompt_image(uri=image.url, mime_type=image.mime_type) for image in self._image_registry.images]

    def prompt_documents(self) -> list[PromptDocument]:
        """Every referenced document in the order its token numbers it."""
        return list(self._documents.values())

    def _register_direct_image(self, *, image_reference: ImageReference, context_provider: ContextProviderAbstract) -> None:
        try:
            image_content = context_provider.get_typed_object_or_attribute(
                name=image_reference.variable_path,
                wanted_type=ImageContent,
                accept_list=False,
            )
        except ContextProviderError as exc:
            msg = f"Could not find image '{image_reference.variable_path}' in context: {exc}"
            raise PromptContentError(msg) from exc
        if not isinstance(image_content, ImageContent):
            msg = f"Image reference '{image_reference.variable_path}' is of type '{type(image_content).__name__}', expected ImageContent"
            raise PromptContentError(msg)
        self._image_registry_indices[image_reference.variable_path] = self._image_registry.register_image(image_content)

    def _register_direct_list_images(self, *, image_reference: ImageReference, context_provider: ContextProviderAbstract) -> None:
        try:
            image_items = context_provider.get_typed_object_or_attribute(
                name=image_reference.variable_path,
                wanted_type=ImageContent,
                accept_list=True,
            )
        except ContextProviderError as exc:
            msg = f"Could not find image list '{image_reference.variable_path}' in context: {exc}"
            raise PromptContentError(msg) from exc
        if not isinstance(image_items, (list, tuple)):
            msg = (
                f"Image list reference '{image_reference.variable_path}' is of type '{type(image_items).__name__}', "
                "expected list or tuple of ImageContent"
            )
            raise PromptContentError(msg)
        for list_position, image_item in enumerate(cast("list[Any] | tuple[Any, ...]", image_items), start=1):
            if not isinstance(image_item, ImageContent):
                msg = f"Item of '{image_reference.variable_path}' is of type '{type(image_item).__name__}', expected ImageContent"
                raise PromptContentError(msg)
            # Keyed by the 1-based list position, numbered by the registry index.
            self._image_registry_indices[f"{image_reference.variable_path}[{list_position}]"] = self._image_registry.register_image(image_item)

    def _register_direct_document(self, *, document_reference: DocumentReference, context_provider: ContextProviderAbstract) -> None:
        try:
            document_content = context_provider.get_typed_object_or_attribute(
                name=document_reference.variable_path,
                wanted_type=DocumentContent,
                accept_list=False,
            )
        except ContextProviderError as exc:
            msg = f"Could not find document '{document_reference.variable_path}' in context: {exc}"
            raise PromptContentError(msg) from exc
        if not isinstance(document_content, DocumentContent):
            msg = f"Document reference '{document_reference.variable_path}' is of type '{type(document_content).__name__}', expected DocumentContent"
            raise PromptContentError(msg)
        self._documents[document_reference.variable_path] = PromptDocumentFactory.make_prompt_document(
            uri=document_content.url,
            mime_type=document_content.mime_type,
        )

    def _register_direct_list_documents(self, *, document_reference: DocumentReference, context_provider: ContextProviderAbstract) -> None:
        try:
            document_items = context_provider.get_typed_object_or_attribute(
                name=document_reference.variable_path,
                wanted_type=DocumentContent,
                accept_list=True,
            )
        except ContextProviderError as exc:
            msg = f"Could not find document list '{document_reference.variable_path}' in context: {exc}"
            raise PromptContentError(msg) from exc
        if not isinstance(document_items, (list, tuple)):
            msg = (
                f"Document list reference '{document_reference.variable_path}' is of type '{type(document_items).__name__}', "
                "expected list or tuple of DocumentContent"
            )
            raise PromptContentError(msg)
        for list_position, document_item in enumerate(cast("list[Any] | tuple[Any, ...]", document_items), start=1):
            if not isinstance(document_item, DocumentContent):
                msg = f"Item of '{document_reference.variable_path}' is of type '{type(document_item).__name__}', expected DocumentContent"
                raise PromptContentError(msg)
            self._documents[f"{document_reference.variable_path}[{list_position}]"] = PromptDocumentFactory.make_prompt_document(
                uri=document_item.url,
                mime_type=document_item.mime_type,
            )


def _image_token(*, registry_index: int) -> str:
    return f"[Image {registry_index + 1}]"
