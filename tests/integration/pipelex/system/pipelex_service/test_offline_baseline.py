"""Pins the offline-mode baseline.

These tests describe the behaviour that must NOT regress:

- BYOK setups (gateway disabled) must complete offline without any remote-config fetch.
- Gateway-enabled setups with no network AND no cache must raise
  ``RemoteConfigUnavailableError`` (the user-facing offline-mode error introduced in Phase 2).
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — referenced by pytest fixture type hints at runtime
from typing import TYPE_CHECKING

import httpx
import pytest

from pipelex import log
from pipelex.pipelex import Pipelex
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.pipelex_service.exceptions import RemoteConfigUnavailableError
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

    def test_gateway_offline_without_cache_raises_remote_config_unavailable_error(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Gateway enabled + offline + no primed cache → ``RemoteConfigUnavailableError``.

        Phase 2 introduced a cache fallback so the fetcher only raises when both the network
        and the local cache are unusable. We redirect ``~/.pipelex`` to a tmp path so any
        cache the developer has from prior online work doesn't satisfy the fallback.
        """
        Pipelex.teardown_if_needed()

        # Isolate the cache so a real ``~/.pipelex/cache/`` from prior online runs can't
        # accidentally make this test "succeed via cache" and miss the regression.
        mocker.patch.object(
            ConfigLoader,
            "global_config_dir",
            new_callable=mocker.PropertyMock,
            return_value=tmp_path / ".pipelex",
        )

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
        mocker.patch.object(RemoteConfigFetcher, "FETCH_MAX_RETRIES", 1)
        mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))

        try:
            with pytest.raises(RemoteConfigUnavailableError):
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
