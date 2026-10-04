"""GatewayUnknownModelError contract.

When a model deck references a handle that a managed gateway should provide but that gateway's
model specs (fresh or cached) don't contain it, setup must raise ``GatewayUnknownModelError``
with provenance so the message can hint stale-cache remediation. This complements the
existing ``LLMHandleNotFoundError`` path: the gateway-specific check fires even when
``missing_presets_reaction = "log"`` (the default), because stale gateway specs are a
distinct, user-actionable failure mode that deserves its own error class.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex import log
from pipelex.cogt.exceptions import GatewayUnknownModelError
from pipelex.cogt.model_backends.backend import MANIFOLD_MODEL_SPECS_SECTION, PipelexBackend
from pipelex.pipelex import Pipelex
from pipelex.system.configuration.config_loader import ConfigLoader, config_manager
from pipelex.system.pipelex_service.remote_config import RemoteConfig
from pipelex.system.pipelex_service.remote_config_fetcher import (
    RemoteConfigFetcher,
    RemoteConfigResult,
)
from pipelex.system.pipelex_service.types import RemoteConfigSource
from pipelex.system.runtime import IntegrationMode
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

MANIFOLD_ROUTING_PROFILE = "all_pipelex_manifold"


def _empty_manifold_remote_config_result(source: RemoteConfigSource) -> RemoteConfigResult:
    """Build a ``RemoteConfigResult`` whose manifold section has no model specs.

    Forces every deck-referenced handle that should come from the manifold to be missing,
    so the membership check trips on the first one.
    """
    config = RemoteConfig(**{MANIFOLD_MODEL_SPECS_SECTION: {}})
    return RemoteConfigResult(config=config, source=source, cached_at=None)


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: each test handles its own ``Pipelex.make``."""
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture
def manifold_routed_boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Boot on the repository's inference documents with the manifold enabled and every model routed to it.

    The membership check only judges the handles the active profile routes to a managed backend, so
    enabling the manifold is not enough: the default profile tries it last, after every BYOK backend
    that serves the same model. Both sequences are pinned whole, so a personal override on this machine
    cannot route the boot elsewhere. The manifold's variables are set, or the loader would disable it
    before ever reading its specs.
    """
    routing_profiles_doc = load_toml_with_tomlkit(str(config_manager.routing_profiles_file_path))
    routing_profiles_doc["active"] = MANIFOLD_ROUTING_PROFILE
    routing_profiles_path = tmp_path / "routing_profiles.toml"
    save_toml_to_path(routing_profiles_doc, path=str(routing_profiles_path))

    backends_base_path = Path(config_manager.backends_file_path)
    backends_override_path = tmp_path / "backends_override.toml"
    backends_override_path.write_text(f"[{PipelexBackend.MANIFOLD}]\nenabled = true\n", encoding="utf-8")

    def pinned_routing_profiles_file_paths(_self: object, **_kwargs: object) -> list[Path]:
        return [routing_profiles_path]

    def pinned_backends_file_paths(_self: object, **_kwargs: object) -> list[Path]:
        return [backends_base_path, backends_override_path]

    monkeypatch.setattr(ConfigLoader, "routing_profiles_file_paths", pinned_routing_profiles_file_paths)
    monkeypatch.setattr(ConfigLoader, "backends_file_paths", pinned_backends_file_paths)
    monkeypatch.setenv("PIPELEX_MANIFOLD_ENDPOINT", "https://manifold.example.test/v1")
    monkeypatch.setenv("PIPELEX_MANIFOLD_API_KEY", "test-manifold-key")


class TestGatewayUnknownModel:
    def test_known_model_loads(self) -> None:
        """Happy path: with no managed gateway enabled by default, the membership check has
        nothing to validate and setup is silent.
        """
        Pipelex.teardown_if_needed()
        try:
            Pipelex.make(
                integration_mode=IntegrationMode.PYTEST,
                needs_inference=False,
                needs_model_specs=True,
            )
        finally:
            Pipelex.teardown_if_needed()
            log.reset()

    @pytest.mark.usefixtures("manifold_routed_boot")
    def test_unknown_model_fresh_raises(self, mocker: MockerFixture) -> None:
        """The manifold section carries no model specs → the first deck-referenced handle trips
        ``GatewayUnknownModelError(source=FRESH)`` with the missing model name surfaced.
        """
        Pipelex.teardown_if_needed()
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(
            RemoteConfigFetcher,
            "fetch_remote_config",
            return_value=_empty_manifold_remote_config_result(RemoteConfigSource.FRESH),
        )

        try:
            with pytest.raises(GatewayUnknownModelError) as exc_info:
                Pipelex.make(
                    integration_mode=IntegrationMode.PYTEST,
                    needs_inference=False,
                    needs_model_specs=True,
                )
            assert exc_info.value.source == RemoteConfigSource.FRESH
            assert exc_info.value.model_name, "the error must carry the missing model name"
            assert exc_info.value.model_name in str(exc_info.value), "the error message must surface the missing model name"
            assert exc_info.value.backend_name == PipelexBackend.MANIFOLD, "with more than one managed gateway, the error has to say which"
        finally:
            Pipelex.teardown_if_needed()
            log.reset()

    @pytest.mark.usefixtures("manifold_routed_boot")
    def test_dummy_specs_path_skips_membership_check(self, mocker: MockerFixture) -> None:
        """When a managed gateway is enabled but ``needs_model_specs=False``, ``Pipelex.setup`` builds
        a dummy ``RemoteConfig`` with empty sections. The membership check must NOT run on this
        path — its provenance is "no live gateway data," so validating the deck's handles against
        an empty spec set would always fail. This covers read-only
        flows like ``pipelex-agent models`` (no ``--backend``) where the user did not opt in to
        fetching specs.
        """
        Pipelex.teardown_if_needed()
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        # Spy on the real fetcher: setup must not call it when needs_model_specs=False.
        fetch_spy = mocker.spy(RemoteConfigFetcher, "fetch_remote_config")

        try:
            # No ``pytest.raises`` — the contract here is exactly that setup succeeds.
            Pipelex.make(
                integration_mode=IntegrationMode.PYTEST,
                needs_inference=False,
                needs_model_specs=False,
            )
            assert fetch_spy.call_count == 0, "needs_model_specs=False must skip the remote fetch entirely (dummy config path)"
        finally:
            Pipelex.teardown_if_needed()
            log.reset()

    @pytest.mark.usefixtures("manifold_routed_boot")
    def test_unknown_model_cached_raises_with_stale_hint(self, mocker: MockerFixture) -> None:
        """Same scenario as fresh, but the remote config came from the cache → the error
        message must point at ``pipelex init`` (while online) to refresh the cache.
        """
        Pipelex.teardown_if_needed()
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(
            RemoteConfigFetcher,
            "fetch_remote_config",
            return_value=_empty_manifold_remote_config_result(RemoteConfigSource.CACHED),
        )

        try:
            with pytest.raises(GatewayUnknownModelError) as exc_info:
                Pipelex.make(
                    integration_mode=IntegrationMode.PYTEST,
                    needs_inference=False,
                    needs_model_specs=True,
                )
            assert exc_info.value.source == RemoteConfigSource.CACHED
            assert "pipelex init" in str(exc_info.value), "the cached-source variant must hint at re-priming via `pipelex init`"
        finally:
            Pipelex.teardown_if_needed()
            log.reset()
