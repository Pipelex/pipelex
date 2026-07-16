"""Tests for MistralFactory message construction: simple messages, chunk conversion, OpenAI-typed messages, and token usage mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from mistralai.models import DocumentURLChunk, ImageURLChunk, SystemMessage, TextChunk, UsageInfo, UserMessage

from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.tools.misc.filetype_utils import FileType
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

PNG_FILE_TYPE = FileType(extension="png", mime="image/png")
PDF_FILE_TYPE = FileType(extension="pdf", mime="application/pdf")


def _make_llm_job(
    mocker: MockerFixture,
    *,
    user_text: str | None = None,
    user_images: list[Any] | None = None,
    user_documents: list[Any] | None = None,
    system_text: str | None = None,
    image_detail: PromptImageDetail | None = None,
) -> Any:
    """Create a mock LLM job exposing only the prompt fields read by MistralFactory."""
    llm_job = mocker.MagicMock()
    llm_job.llm_prompt.user_text = user_text
    llm_job.llm_prompt.user_images = user_images
    llm_job.llm_prompt.user_documents = user_documents
    llm_job.llm_prompt.system_text = system_text
    llm_job.job_params.image_detail = image_detail
    return llm_job


@pytest.mark.asyncio(loop_scope="class")
class TestMistralFactoryMessages:
    # ---- make_simple_messages ----

    async def test_make_simple_messages_text_only(self, mocker: MockerFixture) -> None:
        """A text-only prompt yields a single UserMessage holding one TextChunk with the exact text."""
        factory = MistralFactory()
        messages = await factory.make_simple_messages(llm_job=_make_llm_job(mocker, user_text="Describe the picture"))

        assert len(messages) == 1
        user_message = messages[0]
        assert isinstance(user_message, UserMessage)
        assert isinstance(user_message.content, list)
        assert len(user_message.content) == 1
        text_chunk = user_message.content[0]
        assert isinstance(text_chunk, TextChunk)
        assert text_chunk.text == "Describe the picture"

    async def test_make_simple_messages_system_first_then_user(self, mocker: MockerFixture) -> None:
        """The SystemMessage comes FIRST, followed by the UserMessage, matching the docstring and the OpenAI-typed sibling."""
        factory = MistralFactory()
        messages = await factory.make_simple_messages(llm_job=_make_llm_job(mocker, user_text="user words", system_text="system words"))

        assert len(messages) == 2
        system_message = messages[0]
        assert isinstance(system_message, SystemMessage)
        assert system_message.content == "system words"
        assert isinstance(messages[1], UserMessage)

    @pytest.mark.parametrize(
        ("system_text", "expected_count"),
        [
            ("only the system speaks", 1),
            (None, 0),
        ],
    )
    async def test_make_simple_messages_without_user_content(
        self,
        mocker: MockerFixture,
        system_text: str | None,
        expected_count: int,
    ) -> None:
        """With no user content, only the system message (if any) is emitted; otherwise the list is empty."""
        factory = MistralFactory()
        messages = await factory.make_simple_messages(llm_job=_make_llm_job(mocker, system_text=system_text))

        assert len(messages) == expected_count
        if system_text is not None:
            system_message = messages[0]
            assert isinstance(system_message, SystemMessage)
            assert system_message.content == system_text

    async def test_make_simple_messages_with_images_preserves_order(self, mocker: MockerFixture) -> None:
        """Image chunks are appended after the text chunk, in the same order as the prompt images."""
        image_one = mocker.MagicMock(name="image_one")
        image_two = mocker.MagicMock(name="image_two")
        prepared_by_image_id: dict[int, Any] = {
            id(image_one): PreparedFileHttpUrl(url="https://example.com/one.png"),
            id(image_two): PreparedFileBase64(base64_data="QUJD", file_type=PNG_FILE_TYPE),
        }

        def fake_prepare_prompt_image(prompt_image: Any, is_http_url_enabled: bool) -> Any:
            assert is_http_url_enabled is True
            return prepared_by_image_id[id(prompt_image)]

        mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prepare_prompt_image",
            side_effect=fake_prepare_prompt_image,
        )

        factory = MistralFactory()
        messages = await factory.make_simple_messages(
            llm_job=_make_llm_job(mocker, user_text="look at these", user_images=[image_one, image_two]),
        )

        assert len(messages) == 1
        user_message = messages[0]
        assert isinstance(user_message, UserMessage)
        assert isinstance(user_message.content, list)
        assert len(user_message.content) == 3
        assert isinstance(user_message.content[0], TextChunk)
        chunk_one = user_message.content[1]
        chunk_two = user_message.content[2]
        assert isinstance(chunk_one, ImageURLChunk)
        assert isinstance(chunk_two, ImageURLChunk)
        assert chunk_one.image_url == "https://example.com/one.png"
        assert chunk_two.image_url == "data:image/png;base64,QUJD"

    async def test_make_simple_messages_with_documents(self, mocker: MockerFixture) -> None:
        """Document chunks are appended in prompt order, each prepared via prep_prompt_documents with HTTP URLs enabled."""
        document_one = mocker.MagicMock(name="document_one")
        document_two = mocker.MagicMock(name="document_two")
        prepared_by_document_id: dict[int, Any] = {
            id(document_one): PreparedFileHttpUrl(url="https://example.com/one.pdf"),
            id(document_two): PreparedFileBase64(base64_data="UERG", file_type=PDF_FILE_TYPE),
        }

        def fake_prep_prompt_documents(prompt_documents: list[Any], is_http_url_enabled: bool) -> list[Any]:
            assert is_http_url_enabled is True
            assert len(prompt_documents) == 1
            return [prepared_by_document_id[id(prompt_documents[0])]]

        mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prep_prompt_documents",
            side_effect=fake_prep_prompt_documents,
        )

        factory = MistralFactory()
        messages = await factory.make_simple_messages(
            llm_job=_make_llm_job(mocker, user_documents=[document_one, document_two]),
        )

        assert len(messages) == 1
        user_message = messages[0]
        assert isinstance(user_message, UserMessage)
        assert isinstance(user_message.content, list)
        assert len(user_message.content) == 2
        chunk_one = user_message.content[0]
        chunk_two = user_message.content[1]
        assert isinstance(chunk_one, DocumentURLChunk)
        assert isinstance(chunk_two, DocumentURLChunk)
        assert chunk_one.document_url == "https://example.com/one.pdf"
        assert chunk_two.document_url == "data:application/pdf;base64,UERG"

    # ---- make_mistral_image_url ----

    @pytest.mark.parametrize(
        ("prepared", "expected_url"),
        [
            (PreparedFileBase64(base64_data="QUJD", file_type=PNG_FILE_TYPE), "data:image/png;base64,QUJD"),
            (PreparedFileHttpUrl(url="https://example.com/pic.png"), "https://example.com/pic.png"),
        ],
    )
    async def test_make_mistral_image_url(
        self,
        mocker: MockerFixture,
        prepared: Any,
        expected_url: str,
    ) -> None:
        """Base64 files become data URLs and HTTP URLs are passed through; HTTP URLs are enabled at preparation."""
        prepare_mock = mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prepare_prompt_image",
            return_value=prepared,
        )
        prompt_image = mocker.MagicMock(name="prompt_image")

        factory = MistralFactory()
        chunk = await factory.make_mistral_image_url(prompt_image=prompt_image)

        assert chunk.image_url == expected_url
        prepare_mock.assert_awaited_once_with(prompt_image=prompt_image, is_http_url_enabled=True)

    async def test_make_mistral_image_url_local_path_raises(self, mocker: MockerFixture) -> None:
        """A PreparedFileLocalPath is rejected with a TypeError for images."""
        mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prepare_prompt_image",
            return_value=PreparedFileLocalPath(path="/fake/dir/pic.png"),
        )

        factory = MistralFactory()
        with pytest.raises(TypeError, match="PreparedFileLocalPath is not supported for images"):
            await factory.make_mistral_image_url(prompt_image=mocker.MagicMock(name="prompt_image"))

    # ---- make_mistral_document_url ----

    @pytest.mark.parametrize(
        ("prepared", "expected_url"),
        [
            (PreparedFileBase64(base64_data="UERG", file_type=PDF_FILE_TYPE), "data:application/pdf;base64,UERG"),
            (PreparedFileHttpUrl(url="https://example.com/file.pdf"), "https://example.com/file.pdf"),
        ],
    )
    async def test_make_mistral_document_url(
        self,
        mocker: MockerFixture,
        prepared: Any,
        expected_url: str,
    ) -> None:
        """Base64 documents become data URLs and HTTP URLs are passed through; HTTP URLs are enabled at preparation."""
        prep_mock = mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prep_prompt_documents",
            return_value=[prepared],
        )
        prompt_document = mocker.MagicMock(name="prompt_document")

        factory = MistralFactory()
        chunk = await factory.make_mistral_document_url(prompt_document=prompt_document)

        assert chunk.document_url == expected_url
        prep_mock.assert_awaited_once_with(prompt_documents=[prompt_document], is_http_url_enabled=True)

    async def test_make_mistral_document_url_local_path_raises(self, mocker: MockerFixture) -> None:
        """A PreparedFileLocalPath is rejected with a TypeError for documents."""
        mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prep_prompt_documents",
            return_value=[PreparedFileLocalPath(path="/fake/dir/file.pdf")],
        )

        factory = MistralFactory()
        with pytest.raises(TypeError, match="PreparedFileLocalPath is not supported for documents"):
            await factory.make_mistral_document_url(prompt_document=mocker.MagicMock(name="prompt_document"))

    # ---- make_simple_messages_openai_typed ----

    @pytest.mark.parametrize(
        ("image_detail", "expected_detail"),
        [
            (None, "auto"),
            (PromptImageDetail.HIGH, "high"),
            (PromptImageDetail.LOW, "low"),
        ],
    )
    async def test_make_simple_messages_openai_typed(
        self,
        mocker: MockerFixture,
        image_detail: PromptImageDetail | None,
        expected_detail: str,
    ) -> None:
        """OpenAI-typed messages put the system message FIRST, then a user message with text and image parts; a missing image_detail maps to AUTO."""
        prep_mock = mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prep_prompt_images",
            return_value=[
                PreparedFileBase64(base64_data="QUJD", file_type=PNG_FILE_TYPE),
                PreparedFileHttpUrl(url="https://example.com/pic.png"),
            ],
        )
        user_images: list[Any] = [mocker.MagicMock(name="image_one"), mocker.MagicMock(name="image_two")]
        llm_job = _make_llm_job(
            mocker,
            user_text="user words",
            user_images=user_images,
            system_text="system words",
            image_detail=image_detail,
        )

        factory = MistralFactory()
        messages = await factory.make_simple_messages_openai_typed(llm_job=llm_job)

        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "system words"}
        user_message = cast("dict[str, Any]", messages[1])
        assert user_message["role"] == "user"
        content_parts = cast("list[dict[str, Any]]", user_message["content"])
        assert len(content_parts) == 3
        assert content_parts[0] == {"text": "user words", "type": "text"}
        assert content_parts[1] == {
            "image_url": {"url": "data:image/png;base64,QUJD", "detail": expected_detail},
            "type": "image_url",
        }
        assert content_parts[2] == {
            "image_url": {"url": "https://example.com/pic.png", "detail": expected_detail},
            "type": "image_url",
        }
        prep_mock.assert_awaited_once_with(prompt_images=user_images, is_http_url_enabled=True)

    async def test_make_simple_messages_openai_typed_local_path_raises(self, mocker: MockerFixture) -> None:
        """A PreparedFileLocalPath image is rejected with a TypeError on the OpenAI-typed path."""
        mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prep_prompt_images",
            return_value=[PreparedFileLocalPath(path="/fake/dir/pic.png")],
        )
        llm_job = _make_llm_job(mocker, user_images=[mocker.MagicMock(name="image_one")])

        factory = MistralFactory()
        with pytest.raises(TypeError, match="PreparedFileLocalPath is not supported for images"):
            await factory.make_simple_messages_openai_typed(llm_job=llm_job)

    # ---- make_nb_tokens_by_category ----

    @pytest.mark.parametrize(
        ("prompt_tokens", "completion_tokens", "expected_input", "expected_output"),
        [
            (120, 45, 120, 45),
            (None, None, 0, 0),
            (None, 7, 0, 7),
        ],
    )
    async def test_make_nb_tokens_by_category(
        self,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        expected_input: int,
        expected_output: int,
    ) -> None:
        """Token usage maps prompt/completion tokens to INPUT/OUTPUT, falling back to 0 when the SDK reports None."""
        usage = UsageInfo(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

        factory = MistralFactory()
        nb_tokens_by_category = factory.make_nb_tokens_by_category(usage=usage)

        assert nb_tokens_by_category == {
            TokenCategory.INPUT: expected_input,
            TokenCategory.OUTPUT: expected_output,
        }
