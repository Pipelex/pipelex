import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.config import get_config
from pipelex.tools.misc.exceptions import RemoteFileFetchError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

FAKE_IMAGE_BYTES = b"fake-image-bytes-for-hashing"


@pytest.mark.asyncio(loop_scope="class")
class TestGeneratedContentFactoryStoredObject:
    @pytest.mark.parametrize(
        ("reported_mime_type", "requested_image_format", "expected_extension", "expected_mime_type"),
        [
            pytest.param("image/jpeg", "png", "jpg", "image/jpeg", id="provider-mime-overrides-requested-format"),
            pytest.param(None, "png", "png", "image/png", id="provider-silent-requested-format-wins"),
        ],
    )
    async def test_stored_object_and_key_follow_resolved_mime_type(
        self,
        mocker: MockerFixture,
        reported_mime_type: str | None,
        requested_image_format: str,
        expected_extension: str,
        expected_mime_type: str,
    ):
        """The stored object's content type and the key's extension follow the reported mime.

        The provider's actual mime type wins over the requested image format, and the requested
        format only fills in when the provider is silent — so the minted key's extension, the
        object's stored content type and the resulting `mime_type` can never diverge (e.g. a
        `.png` key holding `image/jpeg` bytes, or an object a store serves as
        `binary/octet-stream` because it was written without one).
        """
        storage_provider = mocker.MagicMock(spec=StorageProviderAbstract)
        storage_provider.store = mocker.AsyncMock(return_value="pipelex-storage://stored-uri")
        storage_provider.public_url = mocker.AsyncMock(return_value=None)
        factory = GeneratedContentFactory(storage_provider=storage_provider)

        raw_details = GeneratedImageRawDetails(
            size=None,
            actual_bytes=FAKE_IMAGE_BYTES,
            mime_type=reported_mime_type,
            image_format=requested_image_format,
        )

        image_content = await factory.make_image_content(
            storage_scope="test/scope",
            raw_details=raw_details,
        )

        storage_provider.store.assert_awaited_once()
        store_call = storage_provider.store.await_args
        assert store_call is not None
        stored_key: str = store_call.kwargs["key"]
        assert stored_key.startswith("test/scope/generated/")
        assert stored_key.endswith(f".{expected_extension}")
        assert store_call.kwargs["content_type"] == expected_mime_type
        assert image_content.mime_type == expected_mime_type
        assert image_content.url == "pipelex-storage://stored-uri"


@pytest.mark.asyncio(loop_scope="class")
class TestGeneratedContentFactoryFetchedRemoteImage:
    """The fetched-remote path, where nothing has declared a media type yet.

    `GeneratedImageRawDetails` deliberately admits a bare URL with no mime type and no
    image format, on the promise that the type is settled when the bytes are downloaded.
    These are the tests that the promise is kept: the response's own `Content-Type` is
    what the object is stored under, rather than the requested format or a default.
    """

    @pytest.fixture
    def _remote_fetch_enabled(self, mocker: MockerFixture) -> None:
        mocker.patch.object(get_config().runtime.storage, "is_fetch_remote_content_enabled", True)

    @pytest.mark.usefixtures("_remote_fetch_enabled")
    @pytest.mark.parametrize(
        ("declared_mime_type", "requested_image_format", "served_content_type", "expected_extension", "expected_mime_type"),
        [
            pytest.param(None, None, "image/png", "png", "image/png", id="served-type-settles-an-undeclared-image"),
            pytest.param(None, "jpeg", "image/png", "png", "image/png", id="served-type-beats-requested-format"),
            pytest.param(None, None, "application/octet-stream", "jpg", "image/jpeg", id="unsupported-served-type-is-not-stored"),
            pytest.param(None, None, None, "jpg", "image/jpeg", id="silent-server-falls-back-to-default"),
            pytest.param("image/webp", None, "image/png", "webp", "image/webp", id="declared-type-beats-served-type"),
        ],
    )
    async def test_stored_object_follows_the_served_content_type(
        self,
        mocker: MockerFixture,
        declared_mime_type: str | None,
        requested_image_format: str | None,
        served_content_type: str | None,
        expected_extension: str,
        expected_mime_type: str,
    ):
        storage_provider = mocker.MagicMock(spec=StorageProviderAbstract)
        storage_provider.store = mocker.AsyncMock(return_value="pipelex-storage://stored-uri")
        storage_provider.public_url = mocker.AsyncMock(return_value="https://cdn.example/stored")
        mocker.patch(
            "pipelex.cogt.content_generation.generated_content_factory.fetch_file_and_content_type_from_url_httpx",
            new=mocker.AsyncMock(return_value=(FAKE_IMAGE_BYTES, served_content_type)),
        )
        factory = GeneratedContentFactory(storage_provider=storage_provider)

        raw_details = GeneratedImageRawDetails(
            size=None,
            actual_url="https://example.com/generated-image",
            mime_type=declared_mime_type,
            image_format=requested_image_format,
        )

        image_content = await factory.make_image_content(
            storage_scope="test/scope",
            raw_details=raw_details,
        )

        storage_provider.store.assert_awaited_once()
        store_call = storage_provider.store.await_args
        assert store_call is not None
        stored_key: str = store_call.kwargs["key"]
        assert stored_key.endswith(f".{expected_extension}")
        assert store_call.kwargs["content_type"] == expected_mime_type
        assert image_content.mime_type == expected_mime_type

    @pytest.mark.usefixtures("_remote_fetch_enabled")
    async def test_a_failed_fetch_degrades_to_the_remote_url(self, mocker: MockerFixture):
        """A fetch that fails leaves the remote URL standing instead of failing the pipe.

        Every httpx failure reaches this path as `RemoteFileFetchError`, so a fallback
        written against the httpx classes never fired and a 404 escaped `make_image_content`.
        """
        storage_provider = mocker.MagicMock(spec=StorageProviderAbstract)
        storage_provider.store = mocker.AsyncMock(return_value="pipelex-storage://stored-uri")
        storage_provider.public_url = mocker.AsyncMock(return_value=None)
        mocker.patch(
            "pipelex.cogt.content_generation.generated_content_factory.fetch_file_and_content_type_from_url_httpx",
            new=mocker.AsyncMock(side_effect=RemoteFileFetchError("the server answered HTTP 404")),
        )
        factory = GeneratedContentFactory(storage_provider=storage_provider)

        image_content = await factory.make_image_content(
            storage_scope="test/scope",
            raw_details=GeneratedImageRawDetails(size=None, actual_url="https://example.com/gone"),
        )

        storage_provider.store.assert_not_awaited()
        assert image_content.url == "https://example.com/gone"
        assert image_content.public_url == "https://example.com/gone"
