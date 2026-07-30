"""Tests for GatewayCompletionsFactory.make_simple_messages — the override that sends
documents as ``image_url`` parts (which Portkey/Gateway translates per provider).

File preparation is patched at the factory namespace; no filesystem or network access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.providers.gateway.gateway_completions_factory import GatewayCompletionsFactory
from pipelex.tools.misc.filetype_utils import FileType
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_FACTORY_NAMESPACE = "pipelex.providers.gateway.gateway_completions_factory"

_PNG_FILE_TYPE = FileType(extension="png", mime="image/png")
_PDF_FILE_TYPE = FileType(extension="pdf", mime="application/pdf")


def _make_llm_job(
    mocker: MockerFixture,
    system_text: str | None = None,
    user_text: str | None = None,
    has_images: bool = False,
    has_documents: bool = False,
    image_detail: PromptImageDetail | None = None,
) -> Any:
    """Create a mock LLM job carrying just the prompt fields make_simple_messages reads."""
    job = mocker.MagicMock()
    job.llm_prompt.system_text = system_text
    job.llm_prompt.user_text = user_text
    job.llm_prompt.user_images = [mocker.MagicMock()] if has_images else []
    job.llm_prompt.user_documents = [mocker.MagicMock()] if has_documents else []
    job.job_params.image_detail = image_detail
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestGatewayCompletionsMessages:
    """make_simple_messages builds system + user messages with text, image and document parts."""

    async def test_system_and_user_text(self, mocker: MockerFixture) -> None:
        """System text becomes the first message; user text becomes a text content part."""
        factory = GatewayCompletionsFactory(is_http_url_enabled=True)
        llm_job = _make_llm_job(mocker, system_text="You are concise.", user_text="Summarize this.")

        messages = await factory.make_simple_messages(llm_job=llm_job)

        assert messages == [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": [{"type": "text", "text": "Summarize this."}]},
        ]

    @pytest.mark.parametrize(
        ("image_detail", "expected_detail"),
        [
            (None, "auto"),
            (PromptImageDetail.HIGH, "high"),
            (PromptImageDetail.LOW, "low"),
        ],
    )
    async def test_images_become_image_url_parts(
        self,
        mocker: MockerFixture,
        image_detail: PromptImageDetail | None,
        expected_detail: str,
    ) -> None:
        """Base64 images become data-URL image_url parts, HTTP images keep their raw URL,
        and detail comes from job_params.image_detail (defaulting to AUTO).
        """
        factory = GatewayCompletionsFactory(is_http_url_enabled=True)
        llm_job = _make_llm_job(mocker, user_text="Look at these.", has_images=True, image_detail=image_detail)
        prepped_images = [
            PreparedFileBase64(base64_data="QUJD", file_type=_PNG_FILE_TYPE),
            PreparedFileHttpUrl(url="https://img.example/pic.png"),
        ]
        mock_prep_images = mocker.patch(
            f"{_FACTORY_NAMESPACE}.prep_prompt_images",
            new_callable=mocker.AsyncMock,
            return_value=prepped_images,
        )

        messages = await factory.make_simple_messages(llm_job=llm_job)

        mock_prep_images.assert_awaited_once_with(prompt_images=llm_job.llm_prompt.user_images, is_http_url_enabled=True)
        assert len(messages) == 1
        user_message = messages[0]
        assert user_message["role"] == "user"
        user_contents = user_message["content"]
        assert user_contents == [
            {"type": "text", "text": "Look at these."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD", "detail": expected_detail}},
            {"type": "image_url", "image_url": {"url": "https://img.example/pic.png", "detail": expected_detail}},
        ]

    async def test_local_path_image_raises_type_error(self, mocker: MockerFixture) -> None:
        """A PreparedFileLocalPath image is rejected — it should have been converted to base64."""
        factory = GatewayCompletionsFactory(is_http_url_enabled=True)
        llm_job = _make_llm_job(mocker, user_text="text", has_images=True)
        mocker.patch(
            f"{_FACTORY_NAMESPACE}.prep_prompt_images",
            new_callable=mocker.AsyncMock,
            return_value=[PreparedFileLocalPath(path="some/local/pic.png")],
        )

        with pytest.raises(TypeError, match="PreparedFileLocalPath is not supported for images"):
            await factory.make_simple_messages(llm_job=llm_job)

    async def test_base64_document_becomes_image_url_part_with_auto_detail(self, mocker: MockerFixture) -> None:
        """Base64 documents are sent as image_url parts with a data URL and detail='auto',
        and document preparation always disables HTTP URLs regardless of the factory flag.
        """
        factory = GatewayCompletionsFactory(is_http_url_enabled=True)
        llm_job = _make_llm_job(mocker, user_text="Read this doc.", has_documents=True)
        mock_prep_documents = mocker.patch(
            f"{_FACTORY_NAMESPACE}.prep_prompt_documents",
            new_callable=mocker.AsyncMock,
            return_value=[PreparedFileBase64(base64_data="UERG", file_type=_PDF_FILE_TYPE)],
        )

        messages = await factory.make_simple_messages(llm_job=llm_job)

        mock_prep_documents.assert_awaited_once_with(prompt_documents=llm_job.llm_prompt.user_documents, is_http_url_enabled=False)
        assert messages == [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Read this doc."},
                    {"type": "image_url", "image_url": {"url": "data:application/pdf;base64,UERG", "detail": "auto"}},
                ],
            },
        ]

    @pytest.mark.parametrize(
        ("prepped_document", "expected_match"),
        [
            (PreparedFileHttpUrl(url="https://docs.example/file.pdf"), "PreparedFileHttpUrl is not supported for documents"),
            (PreparedFileLocalPath(path="some/local/file.pdf"), "PreparedFileLocalPath is not supported for documents"),
        ],
        ids=["http-url-document", "local-path-document"],
    )
    async def test_non_base64_document_raises_type_error(
        self,
        mocker: MockerFixture,
        prepped_document: PreparedFileHttpUrl | PreparedFileLocalPath,
        expected_match: str,
    ) -> None:
        """HTTP-URL and local-path documents are rejected — only base64 is supported here."""
        factory = GatewayCompletionsFactory(is_http_url_enabled=True)
        llm_job = _make_llm_job(mocker, user_text="text", has_documents=True)
        mocker.patch(
            f"{_FACTORY_NAMESPACE}.prep_prompt_documents",
            new_callable=mocker.AsyncMock,
            return_value=[prepped_document],
        )

        with pytest.raises(TypeError, match=expected_match):
            await factory.make_simple_messages(llm_job=llm_job)
