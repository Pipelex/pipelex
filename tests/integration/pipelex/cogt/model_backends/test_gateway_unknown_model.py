"""GatewayUnknownModelError contract.

When a model deck references a handle that the gateway should provide but the gateway's
model specs (fresh or cached) don't contain it, setup must raise ``GatewayUnknownModelError``
with provenance so the message can hint stale-cache remediation. This complements the
existing ``LLMHandleNotFoundError`` path: the gateway-specific check fires even when
``missing_presets_reaction = "log"`` (the default), because stale gateway specs are a
distinct, user-actionable failure mode that deserves its own error class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex import log
from pipelex.cogt.exceptions import GatewayUnknownModelError
from pipelex.pipelex import Pipelex
from pipelex.system.pipelex_service.remote_config import PipelexPosthogConfig, RemoteConfig
from pipelex.system.pipelex_service.remote_config_fetcher import (
    RemoteConfigFetcher,
    RemoteConfigResult,
)
from pipelex.system.pipelex_service.types import RemoteConfigSource
from pipelex.system.runtime import IntegrationMode

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

PIPELEX_MODULE = "pipelex.pipelex"


def _empty_gateway_remote_config_result(source: RemoteConfigSource) -> RemoteConfigResult:
    """Build a ``RemoteConfigResult`` whose gateway has no model specs.

    Forces every deck-referenced handle that should come from the gateway to be missing,
    so the new membership check trips on the first one.
    """
    config = RemoteConfig(
        posthog=PipelexPosthogConfig(
            project_api_key="",
            endpoint="https://dummy.example.com",
            is_geoip_enabled=False,
            is_debug_enabled=False,
        ),
        backend_model_specs={},
        aws_region="us-east-1",
    )
    return RemoteConfigResult(config=config, source=source, cached_at=None)


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: each test handles its own ``Pipelex.make``."""
    yield
    Pipelex.teardown_if_needed()


class TestGatewayUnknownModel:
    def test_known_model_loads(self) -> None:
        """Happy path: the session-cached gateway config contains every model referenced by
        the default deck, so the new gateway-membership check should be silent.
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

    def test_unknown_model_fresh_raises(self, mocker: MockerFixture) -> None:
        """Gateway returns no model specs → first deck-referenced gateway handle trips
        ``GatewayUnknownModelError(source=FRESH)`` with the missing model name surfaced.
        """
        Pipelex.teardown_if_needed()
        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(
            RemoteConfigFetcher,
            "fetch_remote_config",
            return_value=_empty_gateway_remote_config_result(RemoteConfigSource.FRESH),
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
        finally:
            Pipelex.teardown_if_needed()
            log.reset()

    def test_dummy_specs_path_skips_membership_check(self, mocker: MockerFixture) -> None:
        """When gateway is enabled but ``needs_model_specs=False``, ``Pipelex.setup`` builds a
        dummy ``RemoteConfig`` with empty ``backend_model_specs``. The membership check must NOT
        run on this path — its provenance is "no live gateway data," so validating the deck's
        gateway handles against an empty spec set would always fail. This covers read-only
        flows like ``pipelex-agent models`` (no ``--backend``) where the user did not opt in to
        fetching specs.
        """
        Pipelex.teardown_if_needed()
        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
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

    def test_unknown_model_cached_raises_with_stale_hint(self, mocker: MockerFixture) -> None:
        """Same scenario as fresh, but the gateway config came from the cache → the error
        message must point at ``pipelex init`` (while online) to refresh the cache.
        """
        Pipelex.teardown_if_needed()
        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(
            RemoteConfigFetcher,
            "fetch_remote_config",
            return_value=_empty_gateway_remote_config_result(RemoteConfigSource.CACHED),
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
