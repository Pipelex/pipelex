import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

FAKE_IMAGE_BYTES = b"fake-image-bytes-for-hashing"


@pytest.mark.asyncio(loop_scope="class")
class TestGeneratedContentFactoryStorageKey:
    @pytest.mark.parametrize(
        ("reported_mime_type", "requested_image_format", "expected_extension", "expected_mime_type"),
        [
            pytest.param("image/jpeg", "png", "jpg", "image/jpeg", id="provider-mime-overrides-requested-format"),
            pytest.param(None, "png", "png", "image/png", id="provider-silent-requested-format-wins"),
        ],
    )
    async def test_storage_key_extension_follows_resolved_mime_type(
        self,
        mocker: MockerFixture,
        reported_mime_type: str | None,
        requested_image_format: str,
        expected_extension: str,
        expected_mime_type: str,
    ):
        """The storage-key extension derives from the same mime resolution the result reports.

        The provider's actual mime type wins over the requested image format, and the requested
        format only fills in when the provider is silent — so the minted key's extension and the
        resulting `mime_type` can never diverge (e.g. a `.png` key holding `image/jpeg` bytes).
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
        assert image_content.mime_type == expected_mime_type
        assert image_content.url == "pipelex-storage://stored-uri"
