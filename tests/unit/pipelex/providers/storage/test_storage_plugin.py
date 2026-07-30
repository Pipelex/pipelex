"""The built-in StoragePlugin: registers a factory for every built-in method, and each factory
constructs the matching provider at the boot apply-point.

The construction is deferred — selecting ``s3``/``gcp`` builds the provider without importing its
optional SDK (the SDK guard lives inside the provider's I/O methods, not its ``__init__``), and the
``gcp`` factory reads its credentials from the hub secrets provider at that apply-point. Registration
itself never touches an SDK; the import-light guarantee is pinned by ``test_import_light_boot``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable, cast

import pytest

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.plugins.storage_provider_registry import StorageProviderRegistry
from pipelex.providers.storage.storage_plugin import StoragePlugin
from pipelex.tools.storage.gcp_storage_provider import GcpStorageProvider
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.s3_storage_provider import S3StorageProvider
from pipelex.tools.storage.storage_config import StorageMethod, StorageProviderConfig
from tests.unit.pipelex.tools.storage.test_storage_provider_config import (
    make_gcp_config,
    make_in_memory_config,
    make_local_config,
    make_s3_config,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


class _FakeSecretsProvider:
    """Records which secrets the gcp factory asks for and returns a canned credentials path."""

    def __init__(self, credentials_path: str) -> None:
        self.credentials_path = credentials_path
        self.requested_secret_ids: list[str] = []

    def get_required_secret(self, *, secret_id: str) -> str:
        self.requested_secret_ids.append(secret_id)
        return self.credentials_path


def _build_storage_registry() -> StorageProviderRegistry:
    registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))
    StoragePlugin().register(registrar)
    return StorageProviderRegistry(registrar.storage_providers)


class TestStoragePlugin:
    def test_registers_a_factory_for_every_builtin_method(self) -> None:
        """StoragePlugin is a named, API-versioned builtin registering one factory per StorageMethod value."""
        plugin = StoragePlugin()
        assert plugin.name == "storage"
        assert plugin.targets_api == PLUGIN_API_VERSION

        registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))
        discovery = registrar.begin_plugin(name="storage", origin=PluginOrigin.BUILTIN, targets_api=PLUGIN_API_VERSION)
        plugin.register(registrar)

        # StrEnum keys compare equal to their plain-str form, so boot's plain-str config.method resolves them.
        assert set(registrar.storage_providers) == {"local", "in_memory", "s3", "gcp"}
        assert set(registrar.storage_providers) == set(StorageMethod)
        for method in StorageMethod:
            assert f"storage provider {method}" in discovery.contributions

    @pytest.mark.parametrize(
        ("method", "field_name", "sub_config_factory", "expected_type"),
        [
            pytest.param(StorageMethod.LOCAL, "local", make_local_config, LocalStorageProvider, id="local"),
            pytest.param(StorageMethod.IN_MEMORY, "in_memory", make_in_memory_config, InMemoryStorageProvider, id="in-memory"),
            pytest.param(StorageMethod.S3, "s3", make_s3_config, S3StorageProvider, id="s3"),
        ],
    )
    def test_factory_constructs_the_matching_provider(
        self,
        method: StorageMethod,
        field_name: str,
        sub_config_factory: Callable[[], Any],
        expected_type: type[StorageProviderAbstract],
    ) -> None:
        """Selecting a method through the registry constructs its provider (s3 needs no aioboto3 to build)."""
        registry = _build_storage_registry()
        kwargs: dict[str, Any] = {"method": method, field_name: sub_config_factory()}
        provider = registry.get_required(method=method)(StorageProviderConfig(**kwargs))
        assert isinstance(provider, expected_type)

    def test_gcp_factory_reads_credentials_from_the_hub_secrets_provider(self, mocker: MockerFixture) -> None:
        """The gcp factory resolves GCP_CREDENTIALS_FILE_PATH from the hub secrets provider and passes it through."""
        fake_secrets = _FakeSecretsProvider(credentials_path="/secrets/gcp-creds.json")
        mocker.patch("pipelex.providers.storage.storage_plugin.get_secrets_provider", return_value=fake_secrets)
        # Spy the constructor (wraps → the real provider is still built and returned) to assert the
        # resolved secret value flows through as credentials_file_path, not just that it was requested.
        gcp_ctor = mocker.patch("pipelex.providers.storage.storage_plugin.GcpStorageProvider", wraps=GcpStorageProvider)

        gcp_config = make_gcp_config()
        registry = _build_storage_registry()
        provider = registry.get_required(method=StorageMethod.GCP)(StorageProviderConfig(method=StorageMethod.GCP, gcp=gcp_config))

        assert isinstance(provider, GcpStorageProvider)
        assert fake_secrets.requested_secret_ids == ["GCP_CREDENTIALS_FILE_PATH"]
        gcp_ctor.assert_called_once_with(
            bucket_name=gcp_config.bucket_name,
            project_id=gcp_config.project_id,
            credentials_file_path=fake_secrets.credentials_path,
            signed_urls_lifespan=gcp_config.signed_urls_lifespan,
        )
