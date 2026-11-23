from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import pytest
from typing_extensions import override

from pipelex.plugins.backend_extras_factory import BackendExtrasFactory
from pipelex.providers.anthropic.anthropic_factory import AnthropicFactory
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from tests.helpers.storage_uri_prompt_files import (
    PDF_BYTES,
    PNG_BYTES,
    STORED_IMAGE,
    STORED_PDF,
    content_parts,
    make_stored_files_llm_job,
    mock_storage_load,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec

URL_IMAGE_BLOCK = {"type": "image", "source": {"type": "url", "url": STORED_IMAGE}}
URL_DOCUMENT_BLOCK = {"type": "document", "source": {"type": "url", "url": STORED_PDF}}
BASE64_IMAGE_SOURCE = {"type": "base64", "media_type": "image/png", "data": base64.b64encode(PNG_BYTES).decode("ascii")}
BASE64_DOCUMENT_SOURCE = {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(PDF_BYTES).decode("ascii")}


class _ExtrasFactory(BackendExtrasFactory):
    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return {}, {}


class _OwnInitExtrasFactory(BackendExtrasFactory):
    """A plugin's factory whose own `__init__` never calls the base one."""

    def __init__(self, *, tag: str):
        self.tag = tag

    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return {}, {}


@pytest.mark.asyncio(loop_scope="class")
class TestAnthropicStorageUri:
    async def test_opted_in_the_user_message_carries_url_sources(self, mocker: MockerFixture) -> None:
        """The text call's message sends each stored file as a `url` source, with no storage read."""
        load = mock_storage_load(mocker)

        message = await AnthropicFactory.make_user_message(llm_job=make_stored_files_llm_job(), is_storage_uri_enabled=True)

        parts = content_parts(message)
        assert parts[1:] == [URL_IMAGE_BLOCK, URL_DOCUMENT_BLOCK]
        load.assert_not_called()

    async def test_opted_in_the_structured_messages_carry_url_sources(self, mocker: MockerFixture) -> None:
        """The structured call's messages send each stored file as a `url` source, with no storage read."""
        load = mock_storage_load(mocker)

        messages = await AnthropicFactory.make_simple_messages(llm_job=make_stored_files_llm_job(), is_storage_uri_enabled=True)

        parts = content_parts(messages[-1])
        assert parts[:2] == [URL_IMAGE_BLOCK, URL_DOCUMENT_BLOCK]
        load.assert_not_called()

    @pytest.mark.parametrize("is_structured", [False, True])
    async def test_by_default_the_files_carry_base64_sources(self, mocker: MockerFixture, is_structured: bool) -> None:
        """Off, both builders read each stored file and send it as a `base64` source, as before the opt-in."""
        load = mock_storage_load(mocker)
        llm_job = make_stored_files_llm_job()

        parts: list[dict[str, Any]]
        if is_structured:
            messages = await AnthropicFactory.make_simple_messages(llm_job=llm_job, is_storage_uri_enabled=False)
            parts = content_parts(messages[-1])[:2]
        else:
            message = await AnthropicFactory.make_user_message(llm_job=llm_job, is_storage_uri_enabled=False)
            parts = content_parts(message)[1:]

        assert [part["source"] for part in parts] == [BASE64_IMAGE_SOURCE, BASE64_DOCUMENT_SOURCE]
        assert load.await_count == 2

    @pytest.mark.parametrize(
        ("extras_factory", "expected"),
        [
            (None, False),
            (_ExtrasFactory(), False),
            (_ExtrasFactory(is_storage_uri_enabled=True), True),
            (_OwnInitExtrasFactory(tag="plugin"), False),
        ],
    )
    async def test_the_worker_takes_the_flag_from_its_extras_factory(self, extras_factory: BackendExtrasFactory | None, expected: bool) -> None:
        """A worker built without an extras factory, as every shipped Anthropic backend is, keeps inlining."""
        worker = object.__new__(AnthropicLLMWorker)
        worker.extras_factory = extras_factory

        assert worker._is_storage_uri_enabled is expected  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    async def test_the_worker_passes_the_flag_to_the_text_message(self, mocker: MockerFixture) -> None:
        """`_gen_text` builds its message with the flag its extras factory carries."""
        make_user_message = mocker.patch.object(AnthropicFactory, "make_user_message", new=mocker.AsyncMock(side_effect=RuntimeError("stop")))
        worker = object.__new__(AnthropicLLMWorker)
        worker.extras_factory = _ExtrasFactory(is_storage_uri_enabled=True)
        llm_job = make_stored_files_llm_job()

        with pytest.raises(RuntimeError, match="stop"):
            await worker._gen_text(llm_job=llm_job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        make_user_message.assert_awaited_once_with(llm_job=llm_job, is_storage_uri_enabled=True)
