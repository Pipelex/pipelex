"""`ManifoldCompletionsFactory.make_simple_messages` — the override for a Pipelex-operated gateway.

Documents travel to a Pipelex-operated gateway as a `ChatCompletionContentPartImageParam` holding a
data URL, not as the OpenAI file part the base class sends: the gateway translates that part into
whatever document format the provider it picked actually wants, and it cannot translate a file part.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.providers.manifold.manifold_completions_factory import ManifoldCompletionsFactory
from pipelex.tools.misc.filetype_utils import FileType
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_FACTORY_NAMESPACE = "pipelex.providers.manifold.manifold_completions_factory"

_PNG_FILE_TYPE = FileType(extension="png", mime="image/png")
_PDF_FILE_TYPE = FileType(extension="pdf", mime="application/pdf")


def _make_llm_job(
    mocker: MockerFixture,
    *,
    system_text: str | None = None,
    user_text: str | None = None,
    has_images: bool = False,
    has_documents: bool = False,
    image_detail: PromptImageDetail | None = None,
) -> Any:
    job = mocker.MagicMock()
    job.llm_prompt.system_text = system_text
    job.llm_prompt.user_text = user_text
    job.llm_prompt.user_images = [mocker.MagicMock()] if has_images else []
    job.llm_prompt.user_documents = [mocker.MagicMock()] if has_documents else []
    job.job_params.image_detail = image_detail
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestManifoldCompletionsMessages:
    async def test_system_and_user_text(self, mocker: MockerFixture) -> None:
        factory = ManifoldCompletionsFactory(is_http_url_enabled=False)
        llm_job = _make_llm_job(mocker, system_text="You are concise.", user_text="Summarize this.")

        messages = await factory.make_simple_messages(llm_job=llm_job)

        assert messages == [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": [{"type": "text", "text": "Summarize this."}]},
        ]

    async def test_a_document_travels_as_an_image_url_data_url(self, mocker: MockerFixture) -> None:
        """The whole reason this override exists, and the reason it is not the base class's."""
        factory = ManifoldCompletionsFactory(is_http_url_enabled=False)
        llm_job = _make_llm_job(mocker, user_text="Read this doc.", has_documents=True)
        prep = mocker.patch(
            f"{_FACTORY_NAMESPACE}.prep_prompt_documents",
            new_callable=mocker.AsyncMock,
            return_value=[PreparedFileBase64(base64_data="UERG", file_type=_PDF_FILE_TYPE)],
        )

        messages = await factory.make_simple_messages(llm_job=llm_job)

        # Documents are base64 whatever the factory's images setting allows: an http URL here would
        # reach the gateway as a link it does not fetch.
        prep.assert_awaited_once_with(prompt_documents=llm_job.llm_prompt.user_documents, is_http_url_enabled=False)
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
        ("image_detail", "expected_detail"),
        [(None, "auto"), (PromptImageDetail.HIGH, "high"), (PromptImageDetail.LOW, "low")],
    )
    async def test_images_become_image_url_parts_at_the_requested_detail(
        self,
        mocker: MockerFixture,
        image_detail: PromptImageDetail | None,
        expected_detail: str,
    ) -> None:
        factory = ManifoldCompletionsFactory(is_http_url_enabled=False)
        llm_job = _make_llm_job(mocker, user_text="Look at these.", has_images=True, image_detail=image_detail)
        prep = mocker.patch(
            f"{_FACTORY_NAMESPACE}.prep_prompt_images",
            new_callable=mocker.AsyncMock,
            return_value=[PreparedFileBase64(base64_data="QUJD", file_type=_PNG_FILE_TYPE)],
        )

        messages = await factory.make_simple_messages(llm_job=llm_job)

        prep.assert_awaited_once_with(prompt_images=llm_job.llm_prompt.user_images, is_http_url_enabled=False)
        assert messages == [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Look at these."},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD", "detail": expected_detail}},
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
    async def test_a_document_that_is_not_bytes_is_refused(
        self,
        mocker: MockerFixture,
        prepped_document: PreparedFileHttpUrl | PreparedFileLocalPath,
        expected_match: str,
    ) -> None:
        factory = ManifoldCompletionsFactory(is_http_url_enabled=False)
        llm_job = _make_llm_job(mocker, user_text="text", has_documents=True)
        mocker.patch(f"{_FACTORY_NAMESPACE}.prep_prompt_documents", new_callable=mocker.AsyncMock, return_value=[prepped_document])

        with pytest.raises(TypeError, match=expected_match):
            await factory.make_simple_messages(llm_job=llm_job)
