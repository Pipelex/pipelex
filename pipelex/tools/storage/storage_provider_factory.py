from pathlib import Path

from pipelex import log
from pipelex.hub import get_secrets_provider
from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.tools.storage.gcp_storage_provider import GcpStorageProvider
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.s3_storage_provider import S3StorageProvider
from pipelex.tools.storage.storage_config import StorageConfig, StorageMethod
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


def make_storage_provider_from_config(storage_config: StorageConfig) -> StorageProviderAbstract:
    """Create a storage provider based on the provided storage configuration.

    Args:
        storage_config: The storage configuration specifying method and provider-specific settings.

    Returns:
        A configured storage provider instance.

    Raises:
        PipelexConfigError: If required provider-specific config is missing.
    """
    match storage_config.method:
        case StorageMethod.LOCAL:
            log.verbose(f"Using local storage at: {storage_config.storage_path}")
            return LocalStorageProvider(root_path=Path(storage_config.storage_path))
        case StorageMethod.IN_MEMORY:
            log.verbose("Using in-memory storage")
            return InMemoryStorageProvider()
        case StorageMethod.S3:
            if storage_config.s3 is None:
                msg = "S3 config is required when method is s3"
                raise StorageConfigError(msg)

            storage_config.s3.lazy_validate()
            log.verbose(f"Using S3 storage: bucket={storage_config.s3.bucket_name}, region={storage_config.s3.region}")
            return S3StorageProvider(
                bucket_name=storage_config.s3.bucket_name,
                region=storage_config.s3.region,
                signed_urls_lifespan=storage_config.s3.signed_urls_lifespan,
            )
        case StorageMethod.GCP:
            if storage_config.gcp is None:
                msg = "GCP config is required when method is gcp"
                raise StorageConfigError(msg)
            storage_config.gcp.lazy_validate()
            log.verbose(f"Using GCP storage: bucket={storage_config.gcp.bucket_name}, project={storage_config.gcp.project_id}")
            return GcpStorageProvider(
                bucket_name=storage_config.gcp.bucket_name,
                project_id=storage_config.gcp.project_id,
                credentials_file_path=get_secrets_provider().get_required_secret(secret_id="GCP_CREDENTIALS_FILE_PATH"),
                signed_urls_lifespan=storage_config.gcp.signed_urls_lifespan,
            )
