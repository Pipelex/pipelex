"""Every production entry point that fetches a value's URL raises the refusal rather than absorbing it."""

from collections.abc import Awaitable, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.document.prompt_document_utils import prepare_prompt_document, prepare_prompt_document_as_base64
from pipelex.cogt.file.file_preparation_utils import prepare_file_from_uri
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image, prepare_prompt_image_as_base64
from pipelex.config import get_config
from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.uri_base64 import make_base64_url_from_any_uri, make_base64_url_from_http_url
from tests.unit.pipelex.tools.misc.fetch_ssrf_guard.loopback import SECRET_PATH, LoopbackServer, loopback_url

#: Every production entry point that fetches a value's URL, called the way its callers call it.
FETCHING_CALLERS: list[tuple[str, Callable[[str], Awaitable[object]]]] = [
    ("prepare_prompt_image", lambda url: prepare_prompt_image(PromptImageUri(uri=url), is_http_url_enabled=False)),
    ("prepare_prompt_image_as_base64", lambda url: prepare_prompt_image_as_base64(PromptImageUri(uri=url))),
    ("prepare_prompt_document", lambda url: prepare_prompt_document(PromptDocumentUri(uri=url), is_http_url_enabled=False)),
    ("prepare_prompt_document_as_base64", lambda url: prepare_prompt_document_as_base64(PromptDocumentUri(uri=url))),
    ("prepare_file_from_uri", lambda url: prepare_file_from_uri(url, keep_http_url=False, keep_local_path=False)),
    ("make_base64_url_from_any_uri", make_base64_url_from_any_uri),
    ("make_base64_url_from_http_url", make_base64_url_from_http_url),
]


@pytest.mark.asyncio(loop_scope="class")
class TestCallersSurfaceTheRefusal:
    """No caller absorbs the refusal into a fallback: it reaches the pipe as `SsrfBlockedError`."""

    @pytest.mark.parametrize(
        "call",
        [pytest.param(call, id=caller_name) for caller_name, call in FETCHING_CALLERS],
    )
    async def test_caller_raises_the_refusal(self, loopback_server: LoopbackServer, call: Callable[[str], Awaitable[object]]) -> None:
        with pytest.raises(SsrfBlockedError) as exc_info:
            await call(loopback_url(loopback_server, path=SECRET_PATH))

        assert exc_info.type is SsrfBlockedError
        assert loopback_server.hits == []

    async def test_a_generated_image_url_on_a_private_address_fails_instead_of_degrading(
        self,
        mocker: MockerFixture,
        loopback_server: LoopbackServer,
    ) -> None:
        mocker.patch.object(get_config().runtime.storage, "is_fetch_remote_content_enabled", True)
        storage_provider = mocker.MagicMock(spec=StorageProviderAbstract)
        storage_provider.store = mocker.AsyncMock(return_value="pipelex-storage://stored-uri")
        factory = GeneratedContentFactory(storage_provider=storage_provider)

        with pytest.raises(SsrfBlockedError):
            await factory.make_image_content(
                storage_scope="test/scope",
                raw_details=GeneratedImageRawDetails(size=None, actual_url=loopback_url(loopback_server, path=SECRET_PATH)),
            )

        assert loopback_server.hits == []
        storage_provider.store.assert_not_awaited()
