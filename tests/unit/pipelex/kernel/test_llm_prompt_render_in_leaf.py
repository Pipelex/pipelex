from typing import TYPE_CHECKING, Any

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.llm.unrendered_llm_prompt import UnrenderedLLMPrompt
from pipelex.cogt.templating.prompt_file_registrations import PromptFileRegistrations
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.kernel.llm_prompt_content import LlmPromptContent, assemble_llm_prompt, prepare_llm_prompt, render_llm_prompt
from pipelex.kernel.prompt_references import DocumentReference, DocumentReferenceKind, ImageReference, ImageReferenceKind
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSecurityError
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent

# Stated rather than resolved: these are unit tests over the assembly itself.
_STYLE = TemplatingStyle(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN)

_PHOTO = "pipelex-storage://org/photo.png"
_ALBUM_FIRST = "pipelex-storage://org/album-1.png"
_ALBUM_SECOND = "pipelex-storage://org/album-2.png"
_PAGE_VIEW = "pipelex-storage://org/page-view.png"
_PAGE_FIGURE = "pipelex-storage://org/page-figure.png"
_CLAIM = "pipelex-storage://org/claim.pdf"
_ANNEX_FIRST = "pipelex-storage://org/annex-1.pdf"
_ANNEX_SECOND = "pipelex-storage://org/annex-2.pdf"


_READ_SCOPE = "org_abc"
_READ_KEY = "org_abc/mt_1/run_9/generated/0123abcd/b.txt"
# Outside the read scope: reading it would be refused, so the render only succeeds if it is never read.
_UNREAD_KEY = "org_other/mt_1/run_9/generated/4567abcd/c.txt"


class _Inner(StructuredContent):
    b: TextContent
    c: TextContent


class _Doc(StructuredContent):
    a: _Inner


def _template(source: str) -> TemplateBlueprint:
    return TemplateBlueprint(template=source, category=TemplateCategory.LLM_PROMPT)


def _every_kind_of_file() -> WorkingMemory:
    anything = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
    contents: dict[str, StuffContent] = {
        "note": TextContent(text="Handle with care."),
        "photo": ImageContent(url=_PHOTO, mime_type="image/png"),
        "album": ListContent[ImageContent](items=[ImageContent(url=_ALBUM_FIRST), ImageContent(url=_ALBUM_SECOND)]),
        "page": PageContent(
            text_and_images=TextAndImagesContent(text=TextContent(text="page text"), images=[ImageContent(url=_PAGE_FIGURE)]),
            page_view=ImageContent(url=_PAGE_VIEW),
        ),
        "claim": DocumentContent(url=_CLAIM, mime_type="application/pdf"),
        "annexes": ListContent[DocumentContent](items=[DocumentContent(url=_ANNEX_FIRST), DocumentContent(url=_ANNEX_SECOND)]),
        "unread": TextContent(text="Nothing reads this."),
    }
    stuffs = [StuffFactory.make_stuff(concept=anything, content=content, name=name) for name, content in contents.items()]
    memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=stuffs)
    memory.add_alias(alias="remark", target="note")
    return memory


def _every_kind_of_reference() -> LlmPromptContent:
    return LlmPromptContent(
        system_template=_template("You compare $photo with documents."),
        user_template=_template("$remark Album: $album View: {{ page.page_view }} Claim: $claim Annexes: $annexes\nPage: {{ page | with_images }}"),
        system_image_references=[ImageReference(variable_path="photo", kind=ImageReferenceKind.DIRECT)],
        user_image_references=[
            ImageReference(variable_path="album", kind=ImageReferenceKind.DIRECT_LIST),
            ImageReference(variable_path="page.page_view", kind=ImageReferenceKind.DIRECT),
            ImageReference(variable_path="page", kind=ImageReferenceKind.NESTED),
        ],
        user_document_references=[
            DocumentReference(variable_path="claim", kind=DocumentReferenceKind.DIRECT),
            DocumentReference(variable_path="annexes", kind=DocumentReferenceKind.DIRECT_LIST),
        ],
    )


@pytest.mark.asyncio(loop_scope="class")
class TestLlmPromptRenderInLeaf:
    async def test_the_leaf_renders_what_one_process_assembles(self) -> None:
        """Preparing in the operator and rendering in the leaf gives the prompt, numbering and files of the one-process assembly."""
        extra_params: dict[str, Any] = {"_nb_output": 3}
        assembled = await assemble_llm_prompt(
            prompt_content=_every_kind_of_reference(),
            context_provider=_every_kind_of_file(),
            output_structure_prompt="\nAnswer as JSON.",
            extra_params=extra_params,
            templating_style=_STYLE,
        )

        unrendered_prompt = prepare_llm_prompt(
            prompt_content=_every_kind_of_reference(),
            memory=_every_kind_of_file(),
            output_structure_prompt="\nAnswer as JSON.",
            extra_params=extra_params,
            templating_style=_STYLE,
        )
        # The registrations cross a host runtime's boundary as JSON, and come back as the same registry.
        crossed_files = PromptFileRegistrations.model_validate_json(unrendered_prompt.files.model_dump_json())
        rendered = await render_llm_prompt(
            unrendered_prompt=unrendered_prompt.model_copy(update={"files": crossed_files}),
            read_scope=None,
            storage_provider=None,
        )

        assert rendered == assembled
        assert rendered.system_text == "You compare [Image 1] with documents."
        assert rendered.user_text is not None
        assert rendered.user_text.startswith(
            "Handle with care. Album: [Image 2], [Image 3] View: [Image 4] Claim: [Document 1] Annexes: [Document 2]\n[Document 3]\nPage: "
        )
        assert rendered.user_text.endswith("\nAnswer as JSON.")
        # The figure the `with_images` filter reached while rendering is numbered after every direct image.
        assert [image.uri for image in rendered.user_images if isinstance(image, PromptImageUri)] == [
            _PHOTO,
            _ALBUM_FIRST,
            _ALBUM_SECOND,
            _PAGE_VIEW,
            _PAGE_FIGURE,
        ]
        assert [document.uri for document in rendered.user_documents if isinstance(document, PromptDocumentUri)] == [
            _CLAIM,
            _ANNEX_FIRST,
            _ANNEX_SECOND,
        ]

    async def test_the_registrations_are_taken_before_anything_renders(self) -> None:
        """The figure a filter reaches is registered by the leaf's render, never by the operator's preparation."""
        unrendered_prompt = prepare_llm_prompt(prompt_content=_every_kind_of_reference(), memory=_every_kind_of_file(), templating_style=_STYLE)

        assert [image.url for image in unrendered_prompt.files.images] == [_PHOTO, _ALBUM_FIRST, _ALBUM_SECOND, _PAGE_VIEW]
        assert list(unrendered_prompt.files.documents) == ["claim", "annexes[1]", "annexes[2]"]

    async def test_the_context_holds_only_what_the_prompt_reads(self) -> None:
        """The memory handed to the leaf keeps the stuffs the templates and references name, an alias with its target."""
        unrendered_prompt = prepare_llm_prompt(prompt_content=_every_kind_of_reference(), memory=_every_kind_of_file(), templating_style=_STYLE)

        # What crosses is the transport form, which names the same stuffs and aliases as the typed memory it was packed from.
        context_memory = unrendered_prompt.context.in_process_memory
        assert context_memory is not None
        assert set(context_memory.root) == {"note", "photo", "album", "page", "claim", "annexes"}
        assert context_memory.aliases == {"remark": "note"}
        assert set(unrendered_prompt.context.working_memory_raw["root"]) == set(context_memory.root)
        assert unrendered_prompt.context.working_memory_raw["aliases"] == {"remark": "note"}

    async def test_only_the_stored_values_the_templates_read_are_loaded(self) -> None:
        """`{{ doc.a.b }}` loads `doc.a.b` and never reads `doc.a.c`, a stored value beside it outside the read scope."""
        storage = InMemoryStorageProvider()
        storage.root[_READ_KEY] = b"B-TEXT"
        unread_value = TextContent(url=f"pipelex-storage://{_UNREAD_KEY}")
        doc = _Doc(a=_Inner(b=TextContent(url=f"pipelex-storage://{_READ_KEY}"), c=unread_value))
        anything = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
        memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=[StuffFactory.make_stuff(concept=anything, content=doc, name="doc")])

        unrendered_prompt = prepare_llm_prompt(
            prompt_content=LlmPromptContent(user_template=_template("Read: {{ doc.a.b }}")), memory=memory, templating_style=_STYLE
        )
        rendered = await render_llm_prompt(unrendered_prompt=unrendered_prompt, read_scope=_READ_SCOPE, storage_provider=storage)

        assert rendered.user_text == "Read: B-TEXT"
        assert not unread_value.is_loaded

    @pytest.mark.builds_problems_without_required_params(reason="renders outside any pipe, whose failure location names the pipe")
    @pytest.mark.parametrize(
        ("topic", "user_template_field", "template_owner", "expected_field", "expected_code"),
        [
            ("a PipeLLM prompt", "prompt", TemplateOwner.METHOD, "prompt", CoreCode.SECURITY_TEMPLATE_REFUSED),
            ("Pipelex's structuring prompt", None, TemplateOwner.PIPELEX, None, CoreCode.RUNTIME_UNEXPECTED),
        ],
    )
    async def test_a_refusal_is_located_and_owned_as_the_prompt_says(
        self,
        topic: str,
        user_template_field: str | None,
        template_owner: TemplateOwner,
        expected_field: str | None,
        expected_code: CoreCode,
    ) -> None:
        """A sandbox refusal names the field the prompt carries, none for a template no field holds, and its owner's code."""
        unrendered_prompt = UnrenderedLLMPrompt(
            user_template=_template("{{ lane.__class__ }}"),
            templating_style=_STYLE,
            extra_params={"lane": "express"},
            user_template_field=user_template_field,
            template_owner=template_owner,
        )

        with pytest.raises(Jinja2TemplateSecurityError) as exc_info:
            await render_llm_prompt(unrendered_prompt=unrendered_prompt, read_scope=None, storage_provider=None)

        assert exc_info.value.template_field == expected_field, topic
        assert exc_info.value.to_problem(view=ProblemView.CALLER).code == expected_code, topic
