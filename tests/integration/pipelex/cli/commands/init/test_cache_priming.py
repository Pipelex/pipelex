"""Phase 4 contract: ``prime_remote_config_cache`` writes the on-disk cache during init.

These tests pin the helper's behaviour:

- When the gateway is enabled and terms are accepted, a successful online fetch persists
  the raw payload to ``~/.pipelex/cache/remote_config.json`` (priming).
- When offline at init time, priming logs a yellow warning and continues — the cache stays
  empty, the user has been told, init does not crash.
- When the gateway is disabled in ``backends.toml``, priming is a no-op (BYOK setups have
  nothing to cache).
- When a cache already exists, a fresh fetch overwrites it (refresh, not skip).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path  # ruff: ignore[typing-only-standard-library-import] — referenced by pytest fixture type hints at runtime
from typing import TYPE_CHECKING

import httpx
import pytest
from rich.console import Console

from pipelex.cli.commands.init.command import prime_remote_config_cache
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.pipelex_service.pipelex_service_agreement import (
    PipelexServiceAgreement,
    PipelexServiceOnboarding,
)
from pipelex.system.pipelex_service.pipelex_service_config import PipelexServiceConfig
from pipelex.system.pipelex_service.remote_config_cache import (
    CACHE_SCHEMA_VERSION,
    CachedRemoteConfig,
    RemoteConfigCache,
)
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

INIT_COMMAND_MODULE = "pipelex.cli.commands.init.command"

# Capture the unpatched classmethod at module import — the session conftest replaces
# ``fetch_remote_config`` with a cache shim that bypasses ``httpx``. We need the real
# fetch path so the ``httpx.get`` mock actually gets exercised.
_ORIGINAL_FETCH_REMOTE_CONFIG = RemoteConfigFetcher.fetch_remote_config


def _accepted_service_config() -> PipelexServiceConfig:
    return PipelexServiceConfig(
        agreement=PipelexServiceAgreement(terms_accepted=True),
        onboarding=PipelexServiceOnboarding(inference_setup_completed=True),
    )


def _fake_remote_payload() -> dict[str, object]:
    """Minimal valid payload for ``RemoteConfig.model_validate``."""
    return {
        "posthog": {
            "project_api_key": "test-key",
            "endpoint": "https://example.invalid",
            "is_geoip_enabled": False,
            "is_debug_enabled": False,
        },
        "backend_model_specs": {},
        "aws_region": "us-east-1",
    }


def _store_malformed_cache(remote_config_payload: dict[str, object]) -> None:
    """Drop-in for ``RemoteConfigCache.store`` that writes a structurally valid cache *wrapper*
    whose inner ``raw_config`` does NOT validate as a ``RemoteConfig``.

    Reproduces the case where ``RemoteConfigCache.load()`` succeeds (the wrapper is fine) but the
    cached payload is unusable for offline runs.
    """
    del remote_config_payload  # intentionally discarded — we write a deliberately broken payload
    cached = CachedRemoteConfig(
        schema_version=CACHE_SCHEMA_VERSION,
        cached_at=datetime.now(tz=UTC),
        raw_config={},
    )
    cache_path = RemoteConfigCache.cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(cached.model_dump_json(), encoding="utf-8")


def _make_httpx_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        request=httpx.Request("GET", "https://example.com/remote_config.json"),
        content=json.dumps(payload).encode("utf-8"),
    )


@pytest.fixture
def isolated_cache_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Redirect ``~/.pipelex`` (and therefore the cache) at a tmp path."""
    fake_global_dir = tmp_path / ".pipelex"
    mocker.patch.object(
        ConfigLoader,
        "global_config_dir",
        new_callable=mocker.PropertyMock,
        return_value=fake_global_dir,
    )
    return fake_global_dir


class TestCachePriming:
    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_init_primes_cache_when_online(self, mocker: MockerFixture) -> None:
        """Gateway enabled + terms accepted + online → cache file written under the global dir."""
        mocker.patch(f"{INIT_COMMAND_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{INIT_COMMAND_MODULE}.load_pipelex_service_config_if_exists",
            return_value=_accepted_service_config(),
        )
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _ORIGINAL_FETCH_REMOTE_CONFIG)
        mocker.patch("httpx.get", return_value=_make_httpx_response(_fake_remote_payload()))

        console = mocker.create_autospec(Console, instance=True)
        prime_remote_config_cache(console=console)

        cache_path = RemoteConfigCache.cache_path()
        assert cache_path.exists(), "priming should write the on-disk cache"
        on_disk = json.loads(cache_path.read_text(encoding="utf-8"))
        assert on_disk["raw_config"]["aws_region"] == "us-east-1"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_init_warns_when_offline(self, mocker: MockerFixture) -> None:
        """Gateway enabled + terms accepted + offline + no cache → warn, do not crash, no cache file."""
        mocker.patch(f"{INIT_COMMAND_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{INIT_COMMAND_MODULE}.load_pipelex_service_config_if_exists",
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

        console = mocker.create_autospec(Console, instance=True)
        prime_remote_config_cache(console=console)  # must NOT raise

        cache_path = RemoteConfigCache.cache_path()
        assert not cache_path.exists(), "priming must not create a cache file when offline"
        # Verify the user actually got a visible warning, not a silent swallow.
        printed = " ".join(str(call_args) for call_args in console.print.call_args_list)
        assert "yellow" in printed.lower(), f"priming offline must print a yellow warning; got: {printed!r}"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_init_skips_priming_when_gateway_disabled(self, mocker: MockerFixture) -> None:
        """Gateway disabled in backends → priming is a no-op (no fetch, no cache write)."""
        mocker.patch(f"{INIT_COMMAND_MODULE}.is_pipelex_gateway_enabled", return_value=False)
        fetch_spy = mocker.spy(RemoteConfigFetcher, "fetch_remote_config")
        httpx_get_mock = mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))

        console = mocker.create_autospec(Console, instance=True)
        prime_remote_config_cache(console=console)

        assert fetch_spy.call_count == 0, "priming must not invoke the fetcher when gateway is disabled"
        assert httpx_get_mock.call_count == 0, "priming must not hit the network when gateway is disabled"
        assert not RemoteConfigCache.cache_path().exists(), "no cache should be written when gateway is disabled"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_init_warns_when_offline_with_stale_cache_present(self, mocker: MockerFixture) -> None:
        """Stale cache exists + offline → priming surfaces an error (not a silent success).

        The fetcher with ``require_fresh=True`` refuses to accept a cached fallback, so an
        offline fetch fails even though a usable cache is on disk. The pre-existing cache file
        must NOT be wiped — subsequent offline dry-runs should still be able to use it.
        """
        stale_payload = _fake_remote_payload()
        stale_payload["aws_region"] = "eu-west-1"
        RemoteConfigCache.store(stale_payload)
        cache_path = RemoteConfigCache.cache_path()
        stale_on_disk_before = json.loads(cache_path.read_text(encoding="utf-8"))

        mocker.patch(f"{INIT_COMMAND_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{INIT_COMMAND_MODULE}.load_pipelex_service_config_if_exists",
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

        console = mocker.create_autospec(Console, instance=True)
        prime_remote_config_cache(console=console)  # must NOT raise

        printed = " ".join(str(call_args) for call_args in console.print.call_args_list)
        assert "yellow" in printed.lower(), f"stale-cache-offline priming must warn; got: {printed!r}"
        stale_on_disk_after = json.loads(cache_path.read_text(encoding="utf-8"))
        assert stale_on_disk_after == stale_on_disk_before, "stale cache must be left intact when priming refuses to use it"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_priming_reads_backends_toml_from_target_dir(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """``target_config_dir`` overrides the layered backends.toml so global vs local init
        primes based on the directory being initialized — not on whatever the layered config
        resolves to first.

        Setup:
        - layered ``backends.toml`` (default ``config_manager.backends_file_path``) has gateway DISABLED.
        - target_config_dir's ``backends.toml`` has gateway ENABLED.

        Expected: priming runs (gateway enabled at the target). Without the fix, the helper
        would consult the layered file and skip priming entirely.
        """
        # Layered config says gateway is disabled — without the fix, this is what gets read.
        layered_dir = tmp_path / "layered_dir"
        layered_backends = layered_dir / "inference" / "backends.toml"
        layered_backends.parent.mkdir(parents=True, exist_ok=True)
        layered_backends.write_text("[pipelex_gateway]\nenabled = false\n", encoding="utf-8")
        mocker.patch.object(
            ConfigLoader,
            "backends_file_path",
            new_callable=mocker.PropertyMock,
            return_value=layered_backends,
        )

        # Target init dir says gateway IS enabled. The priming helper must read THIS file.
        target_dir = tmp_path / "target_dir"
        target_backends = target_dir / "inference" / "backends.toml"
        target_backends.parent.mkdir(parents=True, exist_ok=True)
        target_backends.write_text("[pipelex_gateway]\nenabled = true\n", encoding="utf-8")

        # Terms-accepted check still consults the global pipelex_service.toml — keep that mocked
        # as before. Make the fetcher succeed so we can assert the cache is actually written.
        mocker.patch(
            f"{INIT_COMMAND_MODULE}.load_pipelex_service_config_if_exists",
            return_value=_accepted_service_config(),
        )
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _ORIGINAL_FETCH_REMOTE_CONFIG)
        mocker.patch("httpx.get", return_value=_make_httpx_response(_fake_remote_payload()))

        console = mocker.create_autospec(Console, instance=True)
        prime_remote_config_cache(console=console, target_config_dir=target_dir)

        assert RemoteConfigCache.cache_path().exists(), (
            "priming must run (and write the cache) when the TARGET backends.toml has gateway "
            "enabled, even if the layered backends.toml says otherwise"
        )

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_priming_skips_when_target_dir_says_gateway_disabled(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Inverse of the above: target says gateway disabled, layered says enabled → skip.

        Without the fix, the helper would see the layered "enabled" file, try to fetch, and
        write a cache the user did not opt in to. We assert no fetch attempt and no cache file.
        """
        # Layered says gateway enabled — without the fix, this is what gets read.
        layered_dir = tmp_path / "layered_dir"
        layered_backends = layered_dir / "inference" / "backends.toml"
        layered_backends.parent.mkdir(parents=True, exist_ok=True)
        layered_backends.write_text("[pipelex_gateway]\nenabled = true\n", encoding="utf-8")
        mocker.patch.object(
            ConfigLoader,
            "backends_file_path",
            new_callable=mocker.PropertyMock,
            return_value=layered_backends,
        )

        # Target says gateway disabled — priming should respect that and become a no-op.
        target_dir = tmp_path / "target_dir"
        target_backends = target_dir / "inference" / "backends.toml"
        target_backends.parent.mkdir(parents=True, exist_ok=True)
        target_backends.write_text("[pipelex_gateway]\nenabled = false\n", encoding="utf-8")

        fetch_spy = mocker.spy(RemoteConfigFetcher, "fetch_remote_config")
        httpx_get_mock = mocker.patch("httpx.get", side_effect=httpx.ConnectError("should not be called"))

        console = mocker.create_autospec(Console, instance=True)
        prime_remote_config_cache(console=console, target_config_dir=target_dir)

        assert fetch_spy.call_count == 0, "target dir disables the gateway — priming must NOT consult the layered backends.toml"
        assert httpx_get_mock.call_count == 0
        assert not RemoteConfigCache.cache_path().exists()

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_init_warns_when_cache_write_fails(self, mocker: MockerFixture) -> None:
        """Online fetch succeeds but the cache write fails → priming reports failure, not success.

        The fetcher treats the cache write as opportunistic and swallows OSErrors with only a
        stderr warning. If priming trusted the fetch result alone it would report ``primed=True``
        while no usable cache exists, so ``pipelex-agent init`` would emit ``cache_primed: true``
        and a later offline run would hit ``RemoteConfigUnavailableError``.
        """
        mocker.patch(f"{INIT_COMMAND_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{INIT_COMMAND_MODULE}.load_pipelex_service_config_if_exists",
            return_value=_accepted_service_config(),
        )
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _ORIGINAL_FETCH_REMOTE_CONFIG)
        mocker.patch("httpx.get", return_value=_make_httpx_response(_fake_remote_payload()))
        mocker.patch.object(RemoteConfigCache, "store", side_effect=OSError("read-only cache directory"))

        console = mocker.create_autospec(Console, instance=True)
        prime_remote_config_cache(console=console)  # must NOT raise

        cache_path = RemoteConfigCache.cache_path()
        assert not cache_path.exists(), "no cache file should exist when the write failed"
        printed = " ".join(str(call_args) for call_args in console.print.call_args_list)
        assert "yellow" in printed.lower(), f"a failed cache write must surface a yellow warning; got: {printed!r}"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_init_warns_when_cached_payload_is_malformed(self, mocker: MockerFixture) -> None:
        """Online fetch succeeds and a cache file is written, but its inner ``raw_config`` is not
        a valid ``RemoteConfig`` → priming reports failure, not success.

        ``RemoteConfigCache.load()`` validates only the cache *wrapper*, so a malformed inner
        payload would still pass an ``is None`` check. Priming must re-validate the payload as a
        ``RemoteConfig``, otherwise ``pipelex-agent init`` would emit ``cache_primed: true`` while
        a later offline run hits ``RemoteConfigUnavailableError``.
        """
        mocker.patch(f"{INIT_COMMAND_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{INIT_COMMAND_MODULE}.load_pipelex_service_config_if_exists",
            return_value=_accepted_service_config(),
        )
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _ORIGINAL_FETCH_REMOTE_CONFIG)
        mocker.patch("httpx.get", return_value=_make_httpx_response(_fake_remote_payload()))
        mocker.patch.object(RemoteConfigCache, "store", side_effect=_store_malformed_cache)

        console = mocker.create_autospec(Console, instance=True)
        prime_remote_config_cache(console=console)  # must NOT raise

        printed = " ".join(str(call_args) for call_args in console.print.call_args_list)
        assert "yellow" in printed.lower(), f"a malformed cached payload must surface a yellow warning; got: {printed!r}"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_init_does_not_double_prime(self, mocker: MockerFixture) -> None:
        """When a cache already exists, priming online overwrites it (refresh, not skip)."""
        # Pre-populate the cache with a stale snapshot so we can prove the file gets rewritten.
        stale_payload = _fake_remote_payload()
        stale_payload["aws_region"] = "eu-west-1"
        RemoteConfigCache.store(stale_payload)
        cache_path = RemoteConfigCache.cache_path()
        stale_on_disk = json.loads(cache_path.read_text(encoding="utf-8"))
        assert stale_on_disk["raw_config"]["aws_region"] == "eu-west-1"

        mocker.patch(f"{INIT_COMMAND_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(
            f"{INIT_COMMAND_MODULE}.load_pipelex_service_config_if_exists",
            return_value=_accepted_service_config(),
        )
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _ORIGINAL_FETCH_REMOTE_CONFIG)
        mocker.patch("httpx.get", return_value=_make_httpx_response(_fake_remote_payload()))

        console = mocker.create_autospec(Console, instance=True)
        prime_remote_config_cache(console=console)

        fresh_on_disk = json.loads(cache_path.read_text(encoding="utf-8"))
        assert fresh_on_disk["raw_config"]["aws_region"] == "us-east-1", "priming must overwrite the existing cache"
        assert fresh_on_disk["cached_at"] >= stale_on_disk["cached_at"], "refresh must update the timestamp"
