"""End-to-end secrets-provider selection at boot: default env, explicit override, external discovery,
and the storage↔secrets ordering guard.

The built-in ``env`` method is the default and is selected onto the hub by an ordinary boot; an
explicit ``setup(secrets_provider=...)`` still wins ahead of registry selection; a fake external
method token discovered through a ``pipelex.plugins`` entry point is selectable via
``secrets_config.method``. The final test is the ordering guard: with a non-env secrets method AND
``gcp`` storage, storage's gcp factory reads the config-selected secrets provider from the hub —
proving secrets is resolved and set on the hub before storage selection runs.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from typing_extensions import override

from pipelex.pipelex import Pipelex
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.service_hub import get_secrets_provider, get_secrets_provider_registry, get_storage_provider
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.storage.gcp_storage_provider import GcpStorageProvider

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.tools.secrets.secrets_config import SecretsProviderConfig

EXTERNAL_SECRETS_METHOD = "test_secret"
EXTERNAL_PLUGIN_NAME = "test_secrets_ext"
CANNED_CREDENTIALS_PATH = "/secrets/gcp-creds-from-external.json"


class _RecordingSecretsProvider(SecretsProviderAbstract):
    """An out-of-tree provider — its distinct type proves config-selection, and it records which
    secrets were asked of it so the ordering guard can prove storage's gcp arm read *this* provider.
    """

    def __init__(self) -> None:
        self.requested_secret_ids: list[str] = []

    @override
    def get_required_secret(self, secret_id: str) -> str:
        self.requested_secret_ids.append(secret_id)
        return CANNED_CREDENTIALS_PATH

    @override
    def get_optional_secret(self, secret_id: str) -> str | None:
        return None

    @override
    def get_required_secret_specific_version(self, secret_id: str, *, version_id: str) -> str:
        raise NotImplementedError

    @override
    def get_optional_secret_specific_version(self, secret_id: str, *, version_id: str) -> str | None:
        raise NotImplementedError

    @override
    def set_secret_as_env_var(self, secret_id: str, *, version_id: str = "latest") -> None:
        pass


def _make_recording_secrets_provider(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    return _RecordingSecretsProvider()


class _FakeSecretsPlugin:
    """An external plugin contributing one secrets method under the ``test_secret`` token."""

    name = EXTERNAL_PLUGIN_NAME
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_secrets_provider(method=EXTERNAL_SECRETS_METHOD, factory=_make_recording_secrets_provider)


@pytest.fixture(autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots per test and tears down."""
    Pipelex.teardown_if_needed()
    yield
    Pipelex.teardown_if_needed()


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


def _patch_external_secrets_plugin(mocker: MockerFixture) -> None:
    # The entry point resolves to the plugin class (a zero-arg factory); discovery instantiates it.
    fake_entry_point = SimpleNamespace(name=EXTERNAL_PLUGIN_NAME, load=lambda: _FakeSecretsPlugin)
    mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[fake_entry_point])


class TestSecretsExternalPlugin:
    def test_default_config_yields_the_env_provider_on_the_hub(self) -> None:
        """An ordinary boot selects the built-in ``env`` method: an EnvSecretsProvider lands on the hub."""
        Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False)

        assert get_secrets_provider_registry().has(method="env")
        assert isinstance(get_secrets_provider(), EnvSecretsProvider)

    def test_explicit_secrets_provider_wins_over_config_selection(self) -> None:
        """An explicit setup() param is the exact provider on the hub, ahead of registry selection."""
        explicit = EnvSecretsProvider()
        Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False, secrets_provider=explicit)

        assert get_secrets_provider() is explicit

    def test_external_secrets_method_is_discovered_and_selected_onto_the_hub(self, mocker: MockerFixture) -> None:
        """A fake entry point + a config naming its token boots with that external provider on the hub."""
        _patch_external_secrets_plugin(mocker)

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            config_overrides={"pipelex": {"secrets_config": {"method": EXTERNAL_SECRETS_METHOD}}},
        )

        assert get_secrets_provider_registry().has(method=EXTERNAL_SECRETS_METHOD)
        assert isinstance(get_secrets_provider(), _RecordingSecretsProvider)

    def test_config_selected_secrets_provider_is_read_by_storage_gcp_arm_at_boot(self, mocker: MockerFixture) -> None:
        """Ordering guard: with a non-env secrets method AND gcp storage, storage's gcp factory reads the
        config-selected external secrets provider from the hub. Secrets must be resolved and set on the hub
        before storage selection — a regression that reordered them would leave the gcp arm without its
        provider (or reading a stale env default), and this recorded request would not be the external one.
        """
        _patch_external_secrets_plugin(mocker)

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            config_overrides={
                "pipelex": {
                    "secrets_config": {"method": EXTERNAL_SECRETS_METHOD},
                    "storage_config": {"method": "gcp", "gcp": {"bucket_name": "test-bucket", "project_id": "test-project"}},
                }
            },
        )

        storage_provider = get_storage_provider()
        assert isinstance(storage_provider, GcpStorageProvider)
        secrets_provider = get_secrets_provider()
        assert isinstance(secrets_provider, _RecordingSecretsProvider)
        # GCP_CREDENTIALS_FILE_PATH is requested only by storage's gcp factory, so its presence proves the
        # gcp arm read *this* config-selected external provider from the hub at the boot apply-point. (The
        # recorded list also carries the telemetry factory's POSTHOG_* reads — telemetry resolves secrets
        # even earlier — which is why this is a membership check, not an exact-match.)
        assert "GCP_CREDENTIALS_FILE_PATH" in secrets_provider.requested_secret_ids
