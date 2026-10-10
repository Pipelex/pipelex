"""The user-prompt assembly PipeLLM, PipeImgGen and PipeJudge share: tokens, files and their order.

What is easy to get wrong here, and what these cases pin, is the correspondence between the numbered
tokens in the text and the order of the files handed to the model: the registry numbers both, and a
mismatch mislabels which file the prompt is talking about with nothing downstream able to notice.
"""

from typing import Any

import pytest

from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.exceptions import PromptContentError
from pipelex.kernel.prompt_assembly import PromptFiles, UserPromptContent, assemble_user_prompt
from pipelex.kernel.prompt_references import DocumentReference, DocumentReferenceKind, ImageReference, ImageReferenceKind
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

# Stated rather than resolved: these are unit tests over the assembly itself.
_STYLE = TemplatingStyle(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN)

_PHOTO = "pipelex-storage://org/photo.png"
_ALBUM_FIRST = "pipelex-storage://org/album-1.png"
_ALBUM_SECOND = "pipelex-storage://org/album-2.png"
_PAGE_VIEW = "pipelex-storage://org/page-view.png"
_CLAIM = "pipelex-storage://org/claim.pdf"
_ANNEX_FIRST = "pipelex-storage://org/annex-1.pdf"
_ANNEX_SECOND = "pipelex-storage://org/annex-2.pdf"


def _memory(contents: dict[str, StuffContent]) -> WorkingMemory:
    anything = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
    stuffs = [StuffFactory.make_stuff(concept=anything, content=content, name=name) for name, content in contents.items()]
    return WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=stuffs)


def _template(source: str) -> TemplateBlueprint:
    return TemplateBlueprint(template=source, category=TemplateCategory.LLM_PROMPT)


def _every_kind_of_file() -> WorkingMemory:
    return _memory(
        {
            "note": TextContent(text="Handle with care."),
            "photo": ImageContent(url=_PHOTO, mime_type="image/png"),
            "album": ListContent[ImageContent](items=[ImageContent(url=_ALBUM_FIRST), ImageContent(url=_ALBUM_SECOND)]),
            "page": PageContent(text_and_images=TextAndImagesContent(text=TextContent(text="page text")), page_view=ImageContent(url=_PAGE_VIEW)),
            "claim": DocumentContent(url=_CLAIM, mime_type="application/pdf"),
            "annexes": ListContent[DocumentContent](items=[DocumentContent(url=_ANNEX_FIRST), DocumentContent(url=_ANNEX_SECOND)]),
        }
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPromptAssembly:
    async def test_every_reference_kind_gets_the_token_of_its_position(self) -> None:
        """Direct, list and dotted images, and direct and list documents, each numbered where it is handed over."""
        content = UserPromptContent(
            template=_template("$note Photo: $photo Album: $album View: {{ page.page_view }} Claim: $claim Annexes: $annexes"),
            image_references=[
                ImageReference(variable_path="photo", kind=ImageReferenceKind.DIRECT),
                ImageReference(variable_path="album", kind=ImageReferenceKind.DIRECT_LIST),
                ImageReference(variable_path="page.page_view", kind=ImageReferenceKind.DIRECT),
            ],
            document_references=[
                DocumentReference(variable_path="claim", kind=DocumentReferenceKind.DIRECT),
                DocumentReference(variable_path="annexes", kind=DocumentReferenceKind.DIRECT_LIST),
            ],
        )

        assembled = await assemble_user_prompt(prompt_content=content, context_provider=_every_kind_of_file(), templating_style=_STYLE)

        assert assembled.text == (
            "Handle with care. Photo: [Image 1] Album: [Image 2], [Image 3] View: [Image 4] Claim: [Document 1] Annexes: [Document 2]\n[Document 3]"
        )
        assert [image.uri for image in assembled.images if isinstance(image, PromptImageUri)] == [_PHOTO, _ALBUM_FIRST, _ALBUM_SECOND, _PAGE_VIEW]
        assert [document.uri for document in assembled.documents if isinstance(document, PromptDocumentUri)] == [
            _CLAIM,
            _ANNEX_FIRST,
            _ANNEX_SECOND,
        ]

    async def test_each_file_keeps_the_format_its_content_established(self) -> None:
        content = UserPromptContent(
            template=_template("$photo $claim"),
            image_references=[ImageReference(variable_path="photo", kind=ImageReferenceKind.DIRECT)],
            document_references=[DocumentReference(variable_path="claim", kind=DocumentReferenceKind.DIRECT)],
        )

        assembled = await assemble_user_prompt(prompt_content=content, context_provider=_every_kind_of_file(), templating_style=_STYLE)

        (image,) = assembled.images
        (document,) = assembled.documents
        assert isinstance(image, PromptImageUri)
        assert image.mime_type == "image/png"
        assert isinstance(document, PromptDocumentUri)
        assert document.mime_type == "application/pdf"

    async def test_a_text_only_prompt_has_no_files(self) -> None:
        assembled = await assemble_user_prompt(
            prompt_content=UserPromptContent(template=_template("Note: $note")),
            context_provider=_every_kind_of_file(),
            templating_style=_STYLE,
        )

        assert assembled.text == "Note: Handle with care."
        assert assembled.images == []
        assert assembled.documents == []

    async def test_templates_sharing_one_registry_number_one_sequence(self) -> None:
        """A PipeLLM's system prompt registers first, so its image takes the lower number in both texts."""
        memory = _every_kind_of_file()
        prompt_files = PromptFiles.make_from_references(
            context_provider=memory,
            image_references=[
                ImageReference(variable_path="photo", kind=ImageReferenceKind.DIRECT),
                ImageReference(variable_path="album", kind=ImageReferenceKind.DIRECT_LIST),
            ],
            document_references=[],
        )
        template_params = prompt_files.template_params(extra_params=None)

        first_text = await prompt_files.render(
            template_blueprint=_template("First: $photo"), context_provider=memory, extra_params=template_params, templating_style=_STYLE
        )
        second_text = await prompt_files.render(
            template_blueprint=_template("Second: $album"), context_provider=memory, extra_params=template_params, templating_style=_STYLE
        )

        assert first_text == "First: [Image 1]"
        assert second_text == "Second: [Image 2], [Image 3]"
        assert len(prompt_files.prompt_images()) == 3

    async def test_the_callers_extra_params_are_left_untouched(self) -> None:
        extra_params: dict[str, Any] = {"suffix": "!"}
        content = UserPromptContent(
            template=_template("$photo{{ suffix }}"),
            image_references=[ImageReference(variable_path="photo", kind=ImageReferenceKind.DIRECT)],
        )

        assembled = await assemble_user_prompt(
            prompt_content=content, context_provider=_every_kind_of_file(), templating_style=_STYLE, extra_params=extra_params
        )

        assert assembled.text == "[Image 1]!"
        assert extra_params == {"suffix": "!"}

    @pytest.mark.parametrize(
        ("template_source", "image_references", "document_references"),
        [
            pytest.param(
                "Note: $note{% if snapshot %} $snapshot{% endif %}",
                [ImageReference(variable_path="snapshot", kind=ImageReferenceKind.DIRECT, is_optional=True)],
                [],
                id="image",
            ),
            pytest.param(
                "Note: $note{% if receipt %} $receipt{% endif %}",
                [],
                [DocumentReference(variable_path="receipt", kind=DocumentReferenceKind.DIRECT, is_optional=True)],
                id="document",
            ),
            pytest.param(
                "Note: $note{% if case %} $case.photos{% endif %}",
                [ImageReference(variable_path="case.photos", kind=ImageReferenceKind.DIRECT_LIST, is_optional=True)],
                [],
                id="list_of_images",
            ),
            pytest.param(
                "Note: $note{% if case %} $case.annexes{% endif %}",
                [],
                [DocumentReference(variable_path="case.annexes", kind=DocumentReferenceKind.DIRECT_LIST, is_optional=True)],
                id="list_of_documents",
            ),
        ],
    )
    async def test_an_absent_optional_file_is_skipped_so_its_guard_renders_it_out(
        self, template_source: str, image_references: list[ImageReference], document_references: list[DocumentReference]
    ) -> None:
        """An optional input that holds no value gets no number and no file, and the template's guard leaves it out."""
        content = UserPromptContent(template=_template(template_source), image_references=image_references, document_references=document_references)

        assembled = await assemble_user_prompt(prompt_content=content, context_provider=_every_kind_of_file(), templating_style=_STYLE)

        assert assembled.text == "Note: Handle with care."
        assert assembled.images == []
        assert assembled.documents == []

    async def test_a_present_optional_file_is_attached_and_numbered(self) -> None:
        """Being declared optional changes nothing for a file that is there, a dotted path into a present input included."""
        content = UserPromptContent(
            template=_template("$photo, {{ page.page_view }}{% if claim %} $claim{% endif %}"),
            image_references=[
                ImageReference(variable_path="photo", kind=ImageReferenceKind.DIRECT, is_optional=True),
                ImageReference(variable_path="page.page_view", kind=ImageReferenceKind.DIRECT, is_optional=True),
            ],
            document_references=[DocumentReference(variable_path="claim", kind=DocumentReferenceKind.DIRECT, is_optional=True)],
        )

        assembled = await assemble_user_prompt(prompt_content=content, context_provider=_every_kind_of_file(), templating_style=_STYLE)

        assert assembled.text == "[Image 1], [Image 2] [Document 1]"
        assert [image.uri for image in assembled.images if isinstance(image, PromptImageUri)] == [_PHOTO, _PAGE_VIEW]
        assert [document.uri for document in assembled.documents if isinstance(document, PromptDocumentUri)] == [_CLAIM]

    @pytest.mark.parametrize(
        ("image_reference", "message_fragment"),
        [
            pytest.param(
                ImageReference(variable_path="absent", kind=ImageReferenceKind.DIRECT), "Could not find image 'absent'", id="missing_required"
            ),
            pytest.param(ImageReference(variable_path="note", kind=ImageReferenceKind.DIRECT), "Could not find image 'note'", id="not_an_image"),
        ],
    )
    async def test_a_reference_the_context_cannot_satisfy_is_refused(self, image_reference: ImageReference, message_fragment: str) -> None:
        content = UserPromptContent(template=_template("$note"), image_references=[image_reference])

        with pytest.raises(PromptContentError, match=message_fragment):
            await assemble_user_prompt(prompt_content=content, context_provider=_every_kind_of_file(), templating_style=_STYLE)
