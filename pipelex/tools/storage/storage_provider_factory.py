from pathlib import Path

from pipelex import log
from pipelex.hub import get_secrets_provider
from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.tools.storage.gcp_storage_provider import GcpStorageProvider
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.s3_storage_provider import S3StorageProvider
from pipelex.tools.storage.storage_config import StorageMethod, StorageProviderConfig
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


def make_storage_provider_from_config(storage_provider_config: StorageProviderConfig) -> StorageProviderAbstract:
    """Create a storage provider based on the provided storage configuration.

    Args:
        storage_provider_config: The storage configuration specifying method and provider-specific settings.

    Returns:
        A configured storage provider instance.

    Raises:
        StorageConfigError: If the required provider-specific config is missing or fails its lazy_validate checks.
    """
    match storage_provider_config.method:
        case StorageMethod.LOCAL:
            if storage_provider_config.local is None:
                msg = "local config is required when method is local"
                raise StorageConfigError(msg)
            storage_provider_config.local.lazy_validate()
            log.verbose(f"Using local storage at: {storage_provider_config.local.local_storage_path}")
            return LocalStorageProvider(root_path=Path(storage_provider_config.local.local_storage_path))
        case StorageMethod.IN_MEMORY:
            if storage_provider_config.in_memory is None:
                msg = "in_memory config is required when method is in_memory"
                raise StorageConfigError(msg)
            storage_provider_config.in_memory.lazy_validate()
            log.verbose("Using in-memory storage")
            return InMemoryStorageProvider()
        case StorageMethod.S3:
            if storage_provider_config.s3 is None:
                msg = "S3 config is required when method is s3"
                raise StorageConfigError(msg)

            storage_provider_config.s3.lazy_validate()
            log.verbose(f"Using S3 storage: bucket={storage_provider_config.s3.bucket_name}, region={storage_provider_config.s3.region}")
            return S3StorageProvider(
                bucket_name=storage_provider_config.s3.bucket_name,
                region=storage_provider_config.s3.region,
                signed_urls_lifespan=storage_provider_config.s3.signed_urls_lifespan,
            )
        case StorageMethod.GCP:
            if storage_provider_config.gcp is None:
                msg = "GCP config is required when method is gcp"
                raise StorageConfigError(msg)
            storage_provider_config.gcp.lazy_validate()
            log.verbose(f"Using GCP storage: bucket={storage_provider_config.gcp.bucket_name}, project={storage_provider_config.gcp.project_id}")
            return GcpStorageProvider(
                bucket_name=storage_provider_config.gcp.bucket_name,
                project_id=storage_provider_config.gcp.project_id,
                credentials_file_path=get_secrets_provider().get_required_secret(secret_id="GCP_CREDENTIALS_FILE_PATH"),
                signed_urls_lifespan=storage_provider_config.gcp.signed_urls_lifespan,
            )
