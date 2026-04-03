from pathlib import Path

import pytest

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.config import get_config
from pipelex.tools.storage.storage_config import StorageMethod
from pipelex.tools.storage.storage_provider_factory import make_storage_provider_from_config

S3_TEST_BUCKET = "pipelex-storage-test"
GCP_TEST_BUCKET = "pipelex-storage-test"
TEST_SIGNED_URLS_LIFESPAN = 300


@pytest.fixture
def generated_content_factory(tmp_path: Path) -> GeneratedContentFactory:
    """Create a GeneratedContentFactory with storage provider based on config.

    Applies test overrides for bucket names and signed URL lifespans.
    """
    storage_provider_config = get_config().pipelex.storage_config.storage_provider_config
    match storage_provider_config.method:
        case StorageMethod.S3:
            assert storage_provider_config.s3 is not None
            patched_s3_config = storage_provider_config.s3.model_copy(
                update={
                    "bucket_name": S3_TEST_BUCKET,
                    "signed_urls_lifespan_seconds": TEST_SIGNED_URLS_LIFESPAN,
                }
            )
            patched_provider_config = storage_provider_config.model_copy(update={"s3": patched_s3_config})
        case StorageMethod.GCP:
            assert storage_provider_config.gcp is not None
            patched_gcp_config = storage_provider_config.gcp.model_copy(
                update={
                    "bucket_name": GCP_TEST_BUCKET,
                    "signed_urls_lifespan_seconds": TEST_SIGNED_URLS_LIFESPAN,
                }
            )
            patched_provider_config = storage_provider_config.model_copy(update={"gcp": patched_gcp_config})
        case StorageMethod.LOCAL:
            assert storage_provider_config.local is not None
            patched_local_config = storage_provider_config.local.model_copy(
                update={
                    "local_storage_path": tmp_path,
                }
            )
            patched_provider_config = storage_provider_config.model_copy(update={"local": patched_local_config})
        case StorageMethod.IN_MEMORY:
            patched_provider_config = storage_provider_config

    storage_provider = make_storage_provider_from_config(patched_provider_config)
    return GeneratedContentFactory(storage_provider=storage_provider)


@pytest.fixture
def content_generator(generated_content_factory: GeneratedContentFactory) -> ContentGeneratorProtocol:
    """Provide a ContentGeneratorProtocol instance for testing."""
    return ContentGenerator(generated_content_factory=generated_content_factory)
