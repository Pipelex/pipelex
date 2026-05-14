"""Pins the offline-mode baseline before Phase 1+ refactors.

These tests describe the behaviour that must NOT regress as the cache + fallback layer
lands in later phases:

- BYOK setups (gateway disabled) must complete offline without any remote-config fetch.
- Gateway-enabled setups with no network and no cache currently raise ``RemoteConfigFetchError``;
  Phase 2 will replace that error with ``RemoteConfigUnavailableError`` and this test will be
  updated then to track the new semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from pipelex import log
from pipelex.pipelex import Pipelex
from pipelex.system.pipelex_service.exceptions import RemoteConfigFetchError
from pipelex.system.pipelex_service.pipelex_service_agreement import (
    PipelexServiceAgreement,
    PipelexServiceOnboarding,
)
from pipelex.system.pipelex_service.pipelex_service_config import PipelexServiceConfig
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.system.runtime import IntegrationMode

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

PIPELEX_MODULE = "pipelex.pipelex"

# Capture the original classmethod at module import — the session-scoped fixture in the root
# conftest replaces ``RemoteConfigFetcher.fetch_remote_config`` with a wrapper that caches the
# result for the whole test session. We need the unpatched version to exercise the real fetch
# path against a mocked ``httpx.get``.
_ORIGINAL_FETCH_REMOTE_CONFIG = RemoteConfigFetcher.fetch_remote_config


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module sets up and tears down per test."""
    yield
    Pipelex.teardown_if_needed()


class TestOfflineBaseline:
    def test_byok_offline_setup_succeeds_without_fetching_remote_config(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Gateway disabled: setup must succeed with no network and never hit remote config.

        Even with ``needs_model_specs=True``, when the gateway is disabled the fetch is
        unreachable and the BYOK setup should complete normally.
        """
        Pipelex.teardown_if_needed()

        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=False)
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )

        httpx_get_mock = mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))
        fetch_spy = mocker.spy(RemoteConfigFetcher, "fetch_remote_config")

        try:
            Pipelex.make(
                integration_mode=IntegrationMode.PYTEST,
                needs_inference=False,
                needs_model_specs=True,
            )
        finally:
            Pipelex.teardown_if_needed()

        assert fetch_spy.call_count == 0, "fetch_remote_config must not be invoked when gateway is disabled"
        assert httpx_get_mock.call_count == 0, "httpx.get must not be invoked when gateway is disabled"

    def test_gateway_offline_without_cache_raises_remote_config_fetch_error(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Current (pre-Phase-2) behaviour: gateway enabled + offline → ``RemoteConfigFetchError``.

        Phase 2 introduces a cache fallback that returns the cached config instead of raising
        when offline. When that lands, this test will be rewritten to assert the new semantics
        (cache miss → ``RemoteConfigUnavailableError``).
        """
        Pipelex.teardown_if_needed()

        service_config = PipelexServiceConfig(
            agreement=PipelexServiceAgreement(terms_accepted=True),
            onboarding=PipelexServiceOnboarding(inference_setup_completed=True),
        )
        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{PIPELEX_MODULE}.load_pipelex_service_config_if_exists",
            return_value=service_config,
        )
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )

        # Bypass the session-level cache patch from tests/conftest.py so we exercise the real
        # fetch path against a controlled httpx mock.
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _ORIGINAL_FETCH_REMOTE_CONFIG)
        mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))

        try:
            with pytest.raises(RemoteConfigFetchError):
                Pipelex.make(
                    integration_mode=IntegrationMode.PYTEST,
                    needs_inference=False,
                    needs_model_specs=True,
                )
        finally:
            Pipelex.teardown_if_needed()
            # ``Pipelex.make`` clears the singleton on setup failure but does NOT reset the
            # global log state, so subsequent ``Pipelex.make`` calls would crash with
            # "LogConfig is already set". Reset it manually here so other test modules can
            # still spin up a fresh Pipelex instance.
            log.reset()
