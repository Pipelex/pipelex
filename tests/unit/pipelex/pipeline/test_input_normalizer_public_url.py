from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipeline.exceptions import PipelineInputContentError
from pipelex.pipeline.input_normalizer import NormalizableContent, normalize_data_urls_to_storage
from pipelex.tools.storage.exceptions import StorageInvalidUriError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

STORED_INPUT_URI = "pipelex-storage://org/uploads/moodboard.png"
FRESH_SIGNED_URL = "https://pipelex-app-dev.s3.us-west-2.amazonaws.com/org/uploads/moodboard.png?X-Amz-Signature=fresh"
STALE_SIGNED_URL = "https://pipelex-app-dev.s3.us-west-2.amazonaws.com/org/uploads/moodboard.png?X-Amz-Signature=expired"
HTTP_INPUT_URL = "https://example.com/moodboard.png"
CALLER_PUBLIC_URL = "https://cdn.example.com/moodboard.png"

CONTENT_CLASSES = [ImageContent, DocumentContent]


def _memory_with_content(content: NormalizableContent) -> WorkingMemory:
    native_concept_code = NativeConceptCode.IMAGE if isinstance(content, ImageContent) else NativeConceptCode.DOCUMENT
    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=native_concept_code),
        content=content,
        name="visual",
    )
    return WorkingMemoryFactory.make_from_single_stuff(stuff)


async def _normalized_content(content: NormalizableContent) -> Any:
    memory = await normalize_data_urls_to_storage(_memory_with_content(content), storage_scope="test/scope")
    return memory.get_stuff("visual").content


@pytest.mark.asyncio(loop_scope="class")
class TestInputNormalizerPublicUrl:
    @pytest.fixture
    def mock_storage(self, mocker: MockerFixture) -> Any:
        """A storage provider whose signing returns a fresh link, installed where the normalizer looks it up."""
        storage = mocker.Mock(spec=StorageProviderAbstract)
        storage.public_url = mocker.AsyncMock(return_value=FRESH_SIGNED_URL)
        mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=storage)
        return storage

    @pytest.mark.parametrize("content_class", CONTENT_CLASSES)
    async def test_stored_reference_gets_a_signed_public_url(self, mock_storage: Any, content_class: type[NormalizableContent]) -> None:
        """A pipelex-storage:// input is signed through the storage provider, and its url stays the durable reference."""
        normalized = await _normalized_content(content_class(url=STORED_INPUT_URI))

        assert isinstance(normalized, content_class)
        assert normalized.url == STORED_INPUT_URI
        assert normalized.public_url == FRESH_SIGNED_URL
        mock_storage.public_url.assert_awaited_once_with(uri=STORED_INPUT_URI)
        mock_storage.store.assert_not_called()

    @pytest.mark.parametrize("content_class", CONTENT_CLASSES)
    @pytest.mark.usefixtures("mock_storage")
    async def test_stored_reference_replaces_a_carried_public_url(self, content_class: type[NormalizableContent]) -> None:
        """A link carried beside a reference, as a previous run's output passed back in carries one, may have expired: it is re-signed."""
        normalized = await _normalized_content(content_class(url=STORED_INPUT_URI, public_url=STALE_SIGNED_URL))

        assert normalized.url == STORED_INPUT_URI
        assert normalized.public_url == FRESH_SIGNED_URL

    @pytest.mark.parametrize("content_class", CONTENT_CLASSES)
    async def test_stored_reference_keeps_its_link_when_the_provider_has_none(
        self,
        mock_storage: Any,
        content_class: type[NormalizableContent],
    ) -> None:
        """A provider that cannot link, in-memory storage for one, leaves whatever link the input carried."""
        mock_storage.public_url.return_value = None

        carrying = await _normalized_content(content_class(url=STORED_INPUT_URI, public_url=STALE_SIGNED_URL))
        bare = await _normalized_content(content_class(url=STORED_INPUT_URI))

        assert carrying.public_url == STALE_SIGNED_URL
        assert bare.public_url is None

    @pytest.mark.parametrize("content_class", CONTENT_CLASSES)
    async def test_stored_reference_the_provider_refuses_is_an_input_error(
        self,
        mock_storage: Any,
        content_class: type[NormalizableContent],
    ) -> None:
        """A reference the provider refuses as a key, a path escaping local storage for one, is the caller's input fault."""
        mock_storage.public_url.side_effect = StorageInvalidUriError("Invalid key '../../etc/passwd': path traversal detected")

        with pytest.raises(PipelineInputContentError, match="cannot be linked") as exc_info:
            await _normalized_content(content_class(url="pipelex-storage://../../etc/passwd"))

        assert isinstance(exc_info.value.__cause__, StorageInvalidUriError)

    @pytest.mark.parametrize("content_class", CONTENT_CLASSES)
    async def test_http_url_is_its_own_public_url(self, mock_storage: Any, content_class: type[NormalizableContent]) -> None:
        """An http(s) input with no public_url is already public: the url itself becomes the link, with no storage call."""
        normalized = await _normalized_content(content_class(url=HTTP_INPUT_URL))

        assert isinstance(normalized, content_class)
        assert normalized.url == HTTP_INPUT_URL
        assert normalized.public_url == HTTP_INPUT_URL
        mock_storage.public_url.assert_not_called()
        mock_storage.store.assert_not_called()

    @pytest.mark.parametrize("content_class", CONTENT_CLASSES)
    @pytest.mark.usefixtures("mock_storage")
    async def test_http_url_keeps_a_caller_supplied_public_url(self, content_class: type[NormalizableContent]) -> None:
        """A caller who names a different public link for an http(s) input keeps it."""
        normalized = await _normalized_content(content_class(url=HTTP_INPUT_URL, public_url=CALLER_PUBLIC_URL))

        assert normalized.url == HTTP_INPUT_URL
        assert normalized.public_url == CALLER_PUBLIC_URL
