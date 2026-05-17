"""Phase 3 contract: gateway-cache fallback flows through ``Pipelex.make``.

These tests pin the post-refactor behaviour at the Pipelex-setup boundary (the fetcher-level
contract is locked in by ``test_remote_config_fetcher.py``):

- Dry-run setup ``(needs_inference=False, needs_model_specs=True)`` succeeds with a primed
  cache and emits ``RemoteConfigStaleWarning``; cold cache raises ``RemoteConfigUnavailableError``.
- Pipelex telemetry must be disabled whenever the gateway config is cached, even when
  ``needs_inference=True``. Stale config implies stale model identities, so phoning home about
  pipe runs against possibly-stale specs would pollute metrics.
- BYOK with the gateway disabled never reaches ``fetch_remote_config``, regardless of
  ``needs_model_specs``. Explicit regression guard so future refactors can't reintroduce the
  phantom network call described in the original offline-mode bug.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from pathlib import Path  # noqa: TC003 — referenced by pytest fixture type hints at runtime
from typing import TYPE_CHECKING

import httpx
import pytest

from pipelex import log
from pipelex.pipelex import Pipelex
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.pipelex_service.exceptions import (
    RemoteConfigStaleWarning,
    RemoteConfigUnavailableError,
)
from pipelex.system.pipelex_service.pipelex_service_agreement import (
    PipelexServiceAgreement,
    PipelexServiceOnboarding,
)
from pipelex.system.pipelex_service.pipelex_service_config import PipelexServiceConfig
from pipelex.system.pipelex_service.remote_config_cache import RemoteConfigCache
from pipelex.system.pipelex_service.remote_config_fetcher import (
    RemoteConfigFetcher,
    RemoteConfigResult,
)
from pipelex.system.pipelex_service.types import RemoteConfigSource
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerNoOp

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

PIPELEX_MODULE = "pipelex.pipelex"

# Capture the unpatched classmethod at module import — the session conftest replaces
# ``fetch_remote_config`` with a cached shim. We need the real fetch path to exercise the
# httpx mock for the cache-fallback flow.
_ORIGINAL_FETCH_REMOTE_CONFIG = RemoteConfigFetcher.fetch_remote_config


def _accepted_service_config() -> PipelexServiceConfig:
    return PipelexServiceConfig(
        agreement=PipelexServiceAgreement(terms_accepted=True),
        onboarding=PipelexServiceOnboarding(inference_setup_completed=True),
    )


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: each test handles its own ``Pipelex.make``."""
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture
def isolated_cache_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Redirect ``~/.pipelex`` (and therefore the cache) at a tmp path so a developer's real
    cache from prior online runs can't accidentally satisfy the fallback.
    """
    fake_global_dir = tmp_path / ".pipelex"
    mocker.patch.object(
        ConfigLoader,
        "global_config_dir",
        new_callable=mocker.PropertyMock,
        return_value=fake_global_dir,
    )
    return fake_global_dir


class TestSetupWithCache:
    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_setup_succeeds_with_stale_cache_dry_run(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Gateway enabled, network down, cache primed → setup completes and emits
        ``RemoteConfigStaleWarning``. Validates the end-to-end stale-cache UX (dry-run).
        """
        Pipelex.teardown_if_needed()

        # Prime the cache by calling the session-cached fetcher (returns a real config),
        # then store its raw payload via the cache helper. We do this before re-pointing
        # the cache dir... actually the fixture already pointed us to a tmp dir, so
        # ``RemoteConfigCache.store`` will write there.
        session_result = RemoteConfigFetcher.fetch_remote_config()  # patched to session cache
        RemoteConfigCache.store(session_result.config.model_dump(mode="json"))

        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{PIPELEX_MODULE}.load_pipelex_service_config_if_exists",
            return_value=_accepted_service_config(),
        )
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )

        # Restore the real fetcher so the cache fallback path runs.
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _ORIGINAL_FETCH_REMOTE_CONFIG)
        mocker.patch.object(RemoteConfigFetcher, "FETCH_MAX_RETRIES", 1)
        mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                Pipelex.make(
                    integration_mode=IntegrationMode.PYTEST,
                    needs_inference=False,
                    needs_model_specs=True,
                )
            assert any(issubclass(item.category, RemoteConfigStaleWarning) for item in caught), (
                "stale-cache setup must emit RemoteConfigStaleWarning so machine consumers can surface it"
            )
        finally:
            Pipelex.teardown_if_needed()
            log.reset()

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_setup_fails_without_cache_dry_run(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Gateway enabled, network down, no cache → ``RemoteConfigUnavailableError`` surfaces
        from ``Pipelex.make`` (not silently swallowed).
        """
        Pipelex.teardown_if_needed()

        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{PIPELEX_MODULE}.load_pipelex_service_config_if_exists",
            return_value=_accepted_service_config(),
        )
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
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
            log.reset()

    def test_telemetry_disabled_when_source_cached(self, mocker: MockerFixture) -> None:
        """``Pipelex.make(needs_inference=True)`` with a cached gateway config → telemetry
        manager is the no-op variant. Stale specs imply stale model identities; phoning home
        about pipe runs in that state would pollute metrics, so the guard is stricter than
        the plain ``needs_inference and gateway_enabled`` check.
        """
        Pipelex.teardown_if_needed()

        # Reuse the session-cached gateway config so deck validation passes, but re-wrap with
        # ``source=CACHED`` to exercise the stricter telemetry guard.
        session_result = RemoteConfigFetcher.fetch_remote_config()
        cached_result = RemoteConfigResult(
            config=session_result.config,
            source=RemoteConfigSource.CACHED,
            cached_at=datetime.now(tz=timezone.utc),
        )

        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{PIPELEX_MODULE}.load_pipelex_service_config_if_exists",
            return_value=_accepted_service_config(),
        )
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", return_value=cached_result)

        try:
            pipelex_instance = Pipelex.make(
                integration_mode=IntegrationMode.PYTEST,
                needs_inference=True,
            )
            assert isinstance(pipelex_instance.telemetry_manager, TelemetryManagerNoOp), (
                "cached gateway config must downgrade telemetry to no-op, even when needs_inference=True"
            )
        finally:
            Pipelex.teardown_if_needed()
            log.reset()

    def test_byok_offline_regression_guard(self, mocker: MockerFixture) -> None:
        """Gateway disabled in ``backends.toml`` → ``fetch_remote_config`` is never invoked,
        even with ``needs_model_specs=True``. Without this guard a future refactor could
        reintroduce the phantom network call that originally motivated the offline-mode work.
        """
        Pipelex.teardown_if_needed()

        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=False)
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        fetch_spy = mocker.spy(RemoteConfigFetcher, "fetch_remote_config")
        httpx_get_mock = mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))

        try:
            Pipelex.make(
                integration_mode=IntegrationMode.PYTEST,
                needs_inference=False,
                needs_model_specs=True,
            )
        finally:
            Pipelex.teardown_if_needed()
            log.reset()

        assert fetch_spy.call_count == 0, "fetch_remote_config must never be invoked when the gateway is disabled"
        assert httpx_get_mock.call_count == 0, "httpx.get must never be invoked when the gateway is disabled"
