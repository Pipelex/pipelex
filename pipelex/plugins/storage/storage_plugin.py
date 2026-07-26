from pathlib import Path

from pipelex import log
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.service_hub import get_secrets_provider
from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.tools.storage.gcp_storage_provider import GcpStorageProvider
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.s3_storage_provider import S3StorageProvider
from pipelex.tools.storage.storage_config import StorageMethod, StorageProviderConfig
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


def _make_local_storage_provider(config: StorageProviderConfig) -> StorageProviderAbstract:
    if config.local is None:
        msg = "local config is required when method is local"
        raise StorageConfigError(msg)
    config.local.lazy_validate()
    log.verbose(f"Using local storage at: {config.local.local_storage_path}")
    return LocalStorageProvider(root_path=Path(config.local.local_storage_path))


def _make_in_memory_storage_provider(config: StorageProviderConfig) -> StorageProviderAbstract:
    if config.in_memory is None:
        msg = "in_memory config is required when method is in_memory"
        raise StorageConfigError(msg)
    config.in_memory.lazy_validate()
    log.verbose("Using in-memory storage")
    return InMemoryStorageProvider()


def _make_s3_storage_provider(config: StorageProviderConfig) -> StorageProviderAbstract:
    if config.s3 is None:
        msg = "S3 config is required when method is s3"
        raise StorageConfigError(msg)
    config.s3.lazy_validate()
    log.verbose(f"Using S3 storage: bucket={config.s3.bucket_name}, region={config.s3.region}")
    return S3StorageProvider(
        bucket_name=config.s3.bucket_name,
        region=config.s3.region,
        signed_urls_lifespan=config.s3.signed_urls_lifespan,
    )


def _make_gcp_storage_provider(config: StorageProviderConfig) -> StorageProviderAbstract:
    if config.gcp is None:
        msg = "GCP config is required when method is gcp"
        raise StorageConfigError(msg)
    config.gcp.lazy_validate()
    log.verbose(f"Using GCP storage: bucket={config.gcp.bucket_name}, project={config.gcp.project_id}")
    return GcpStorageProvider(
        bucket_name=config.gcp.bucket_name,
        project_id=config.gcp.project_id,
        # Hub secrets read is legal here: the factory runs at the boot apply-point, after the
        # secrets provider is on the hub — never in register().
        credentials_file_path=get_secrets_provider().get_required_secret(secret_id="GCP_CREDENTIALS_FILE_PATH"),
        signed_urls_lifespan=config.gcp.signed_urls_lifespan,
    )


class StoragePlugin:
    """Always-on built-in provider of the local / in_memory / s3 / gcp storage backends.

    Core-unconditional: storage is required infra, so this plugin cannot be disabled into a
    boot with no storage (see ``CORE_UNCONDITIONAL_PLUGIN_NAMES``). It registers one factory per
    built-in method; ``storage_config.method`` selects which one boot invokes. Importing this
    module is import-light — the s3/gcp SDKs load lazily inside their providers, not at register.
    """

    name = "storage"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_storage_provider(method=StorageMethod.LOCAL, factory=_make_local_storage_provider)
        registrar.add_storage_provider(method=StorageMethod.IN_MEMORY, factory=_make_in_memory_storage_provider)
        registrar.add_storage_provider(method=StorageMethod.S3, factory=_make_s3_storage_provider)
        registrar.add_storage_provider(method=StorageMethod.GCP, factory=_make_gcp_storage_provider)
