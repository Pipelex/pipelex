"""End-to-end: an out-of-tree storage plugin discovered through a ``pipelex.plugins`` entry point is
selectable via ``storage_config.method`` and lands on the hub.

This exercises the whole discovery → selection → hub chain the built-in providers ride, with a fake
external method token: a fake entry point loads a plugin registering ``method="test_mem"``, the boot
config selects that token, and the resolved provider is the one set on the hub.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from typing_extensions import override

from pipelex.pipelex import Pipelex
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.runtime_hub import get_storage_provider, get_storage_provider_registry
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract, StoredData

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.tools.storage.storage_config import StorageProviderConfig

EXTERNAL_STORAGE_METHOD = "test_mem"
EXTERNAL_PLUGIN_NAME = "test_storage_ext"


class _FakeExternalStorageProvider(StorageProviderAbstract):
    """A minimal out-of-tree provider — only its distinct type matters to the selection assertion."""

    @override
    async def _load_with_metadata(self, key: str) -> StoredData:
        raise NotImplementedError

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        raise NotImplementedError

    @override
    async def public_url(self, uri: str) -> str | None:
        return None


def _make_fake_external_provider(_config: StorageProviderConfig) -> StorageProviderAbstract:
    return _FakeExternalStorageProvider()


class _FakeStoragePlugin:
    """An external plugin contributing one storage method under the ``test_mem`` token."""

    name = EXTERNAL_PLUGIN_NAME
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_storage_provider(method=EXTERNAL_STORAGE_METHOD, factory=_make_fake_external_provider)


@pytest.fixture(autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots per test and tears down."""
    Pipelex.teardown_if_needed()
    yield
    Pipelex.teardown_if_needed()


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestStorageExternalPlugin:
    def test_explicit_storage_provider_wins_over_config_selection(self) -> None:
        """An explicit setup() param is the exact provider on the hub, ahead of registry selection."""
        explicit = _FakeExternalStorageProvider()
        Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False, storage_provider=explicit)

        assert get_storage_provider() is explicit

    def test_external_storage_method_is_discovered_and_selected_onto_the_hub(self, mocker: MockerFixture) -> None:
        """A fake entry point + a config naming its token boots with that external provider on the hub."""
        # The entry point resolves to the plugin class (a zero-arg factory); discovery instantiates it.
        fake_entry_point = SimpleNamespace(name=EXTERNAL_PLUGIN_NAME, load=lambda: _FakeStoragePlugin)
        mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[fake_entry_point])

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            config_overrides={"pipelex": {"storage_config": {"method": EXTERNAL_STORAGE_METHOD}}},
        )

        assert get_storage_provider_registry().has(method=EXTERNAL_STORAGE_METHOD)
        assert isinstance(get_storage_provider(), _FakeExternalStorageProvider)
