"""Phase 2 contract for ``RemoteConfigFetcher.fetch_remote_config``.

These tests pin the post-refactor semantics:

- success → ``RemoteConfigResult(source=FRESH)`` AND the cache is written
- network/HTTP failure with a usable cache → ``RemoteConfigResult(source=CACHED)`` with a
  ``cached_at`` timestamp. Warning emission lives at the orchestration layer
  (``Pipelex.setup``), not here — the fetcher is a pure data-returning function.
- failure with no cache → ``RemoteConfigUnavailableError`` (cache path in the message)
- malformed JSON → ``RemoteConfigValidationError`` (no silent cache fallback — server-side bug)
- ``require_fresh=True`` (used by the doc generators) refuses cached fallback
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 — referenced by pytest fixture type hints at runtime
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.pipelex_service.exceptions import (
    RemoteConfigFetchError,
    RemoteConfigUnavailableError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.remote_config import RemoteConfig
from pipelex.system.pipelex_service.remote_config_cache import RemoteConfigCache
from pipelex.system.pipelex_service.remote_config_fetcher import (
    RemoteConfigFetcher,
    RemoteConfigResult,
)
from pipelex.system.pipelex_service.types import RemoteConfigSource

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

# Bypass the session-scoped cache patch in tests/conftest.py.
_ORIGINAL_FETCH_REMOTE_CONFIG = RemoteConfigFetcher.fetch_remote_config


def _valid_remote_config_payload() -> dict[str, Any]:
    return {
        "posthog": {
            "project_api_key": "test-key",
            "endpoint": "https://posthog.example.com",
            "is_geoip_enabled": False,
            "is_debug_enabled": False,
        },
        "backend_model_specs": {"defaults": {"sdk": "gateway_completions"}},
        "aws_region": "eu-west-3",
    }


def _make_httpx_response(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        request=httpx.Request("GET", "https://example.com/remote_config.json"),
        content=json.dumps(payload).encode("utf-8"),
    )


@pytest.fixture
def isolated_cache_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Redirect ``RemoteConfigCache`` at a tmp ``~/.pipelex`` so tests stay hermetic."""
    fake_global_dir = tmp_path / ".pipelex"
    mocker.patch.object(
        ConfigLoader,
        "global_config_dir",
        new_callable=mocker.PropertyMock,
        return_value=fake_global_dir,
    )
    return fake_global_dir


@pytest.fixture(autouse=True)
def restore_original_fetcher(mocker: MockerFixture) -> None:
    """Undo the session-level cached fetch shim from tests/conftest.py."""
    mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", _ORIGINAL_FETCH_REMOTE_CONFIG)


@pytest.fixture(autouse=True)
def disable_codex_cloud(mocker: MockerFixture) -> None:
    """Keep the Codex Cloud short-circuit out of the way for all tests in this module."""
    mocker.patch(
        "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
        new_callable=mocker.PropertyMock,
        return_value=False,
    )


@pytest.fixture
def fast_retry(mocker: MockerFixture) -> None:
    """Collapse tenacity's wait/stop so transient-failure tests don't sleep."""
    mocker.patch.object(RemoteConfigFetcher, "FETCH_WAIT_MIN", 0)
    mocker.patch.object(RemoteConfigFetcher, "FETCH_WAIT_MAX", 0)
    mocker.patch.object(RemoteConfigFetcher, "FETCH_WAIT_MULTIPLIER", 0)


class TestRemoteConfigFetcher:
    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_success_returns_fresh_and_writes_cache(self, mocker: MockerFixture) -> None:
        payload = _valid_remote_config_payload()
        mocker.patch("httpx.get", return_value=_make_httpx_response(payload))

        result = RemoteConfigFetcher.fetch_remote_config()

        assert isinstance(result, RemoteConfigResult)
        assert result.source == RemoteConfigSource.FRESH
        assert result.cached_at is None
        assert result.config.aws_region == "eu-west-3"

        cached = RemoteConfigCache.load()
        assert cached is not None, "successful fetch must persist the raw payload to the cache"
        assert cached.raw_config == payload

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_network_failure_with_cache_returns_cached(self, mocker: MockerFixture) -> None:
        """Cache fallback returns the cached payload tagged ``source=CACHED`` with a
        ``cached_at`` timestamp forwarded verbatim from the on-disk snapshot — not a
        fabricated "now" — so callers can reason about staleness accurately. Warning
        emission lives at the orchestration layer (``Pipelex.setup``); the fetcher itself
        stays a pure data-returning function.
        """
        payload = _valid_remote_config_payload()
        RemoteConfigCache.store(payload)
        stored_snapshot = RemoteConfigCache.load()
        assert stored_snapshot is not None

        mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))
        mocker.patch.object(RemoteConfigFetcher, "FETCH_MAX_RETRIES", 1)

        result = RemoteConfigFetcher.fetch_remote_config()

        assert result.source == RemoteConfigSource.CACHED
        assert result.cached_at == stored_snapshot.cached_at, "result must forward the cache's snapshot timestamp, not a freshly-computed one"
        assert result.config.aws_region == "eu-west-3"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_network_failure_without_cache_raises_unavailable(self, mocker: MockerFixture) -> None:
        mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))
        mocker.patch.object(RemoteConfigFetcher, "FETCH_MAX_RETRIES", 1)

        expected_cache_path = str(RemoteConfigCache.cache_path())

        with pytest.raises(RemoteConfigUnavailableError) as exc_info:
            RemoteConfigFetcher.fetch_remote_config()

        assert expected_cache_path in str(exc_info.value), "error message must name the cache path so users can prime it"
        assert "pipelex init" in str(exc_info.value), "error message must point at the remediation command"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_http_error_with_cache_returns_cached(self, mocker: MockerFixture) -> None:
        """5xx response with a primed cache falls back to cache, same as a connect error.
        Asserts the cached payload (not a fabricated empty one) flows back, with its
        snapshot timestamp preserved.
        """
        payload = _valid_remote_config_payload()
        RemoteConfigCache.store(payload)
        stored_snapshot = RemoteConfigCache.load()
        assert stored_snapshot is not None

        failing_response = httpx.Response(
            status_code=503,
            request=httpx.Request("GET", "https://example.com/remote_config.json"),
            content=b"Service Unavailable",
        )
        mocker.patch("httpx.get", return_value=failing_response)
        mocker.patch.object(RemoteConfigFetcher, "FETCH_MAX_RETRIES", 1)

        result = RemoteConfigFetcher.fetch_remote_config()

        assert result.source == RemoteConfigSource.CACHED
        assert result.cached_at == stored_snapshot.cached_at
        assert result.config.aws_region == "eu-west-3"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_http_error_without_cache_raises_unavailable(self, mocker: MockerFixture) -> None:
        failing_response = httpx.Response(
            status_code=503,
            request=httpx.Request("GET", "https://example.com/remote_config.json"),
            content=b"Service Unavailable",
        )
        mocker.patch("httpx.get", return_value=failing_response)
        mocker.patch.object(RemoteConfigFetcher, "FETCH_MAX_RETRIES", 1)

        with pytest.raises(RemoteConfigUnavailableError):
            RemoteConfigFetcher.fetch_remote_config()

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_validation_error_does_not_fall_back(self, mocker: MockerFixture) -> None:
        """Server-side schema break must surface — we control the server, so a stale cache
        would be the wrong answer here.
        """
        # Cache is populated and otherwise usable; we want to assert it's NOT consulted.
        RemoteConfigCache.store(_valid_remote_config_payload())

        bad_response = httpx.Response(
            status_code=200,
            request=httpx.Request("GET", "https://example.com/remote_config.json"),
            content=b'{"posthog": "not-an-object"}',
        )
        mocker.patch("httpx.get", return_value=bad_response)

        with pytest.raises(RemoteConfigValidationError):
            RemoteConfigFetcher.fetch_remote_config()

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_codex_cloud_short_circuit_still_works(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
            new_callable=mocker.PropertyMock,
            return_value=True,
        )
        httpx_get = mocker.patch("httpx.get")

        result = RemoteConfigFetcher.fetch_remote_config()

        assert result.source == RemoteConfigSource.FRESH
        assert result.cached_at is None
        assert httpx_get.call_count == 0, "Codex Cloud short-circuit must skip the network call"
        assert RemoteConfigCache.load() is None, "Codex Cloud short-circuit must not pollute the cache"

    @pytest.mark.usefixtures("isolated_cache_dir", "fast_retry")
    def test_succeeds_after_4_transient_failures_no_cache_fallback(self, mocker: MockerFixture) -> None:
        payload = _valid_remote_config_payload()
        side_effects: list[Any] = [
            httpx.ConnectError("transient 1"),
            httpx.ConnectError("transient 2"),
            httpx.ConnectError("transient 3"),
            httpx.ConnectError("transient 4"),
            _make_httpx_response(payload),
        ]
        mocker.patch("httpx.get", side_effect=side_effects)

        result = RemoteConfigFetcher.fetch_remote_config()

        assert result.source == RemoteConfigSource.FRESH, "tenacity recovered before exhausting attempts; no cache fallback should trigger"
        cached = RemoteConfigCache.load()
        assert cached is not None
        assert cached.raw_config == payload

    @pytest.mark.usefixtures("isolated_cache_dir", "fast_retry")
    def test_falls_back_to_cache_after_5_transient_failures(self, mocker: MockerFixture) -> None:
        """All retry attempts exhausted, cache primed → cache fallback. Stale-cache warning
        emission is the orchestration layer's concern, so it's not asserted here.
        """
        payload = _valid_remote_config_payload()
        RemoteConfigCache.store(payload)

        mocker.patch("httpx.get", side_effect=httpx.ConnectError("always down"))

        result = RemoteConfigFetcher.fetch_remote_config()

        assert result.source == RemoteConfigSource.CACHED

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_require_fresh_refuses_cache(self, mocker: MockerFixture) -> None:
        """Doc generators set ``require_fresh=True`` so they never bake stale data into committed files.

        When cache is present, the error message must call out that the cache was refused
        (not that it is missing) so the user gets accurate diagnostics.
        """
        RemoteConfigCache.store(_valid_remote_config_payload())
        mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))
        mocker.patch.object(RemoteConfigFetcher, "FETCH_MAX_RETRIES", 1)

        with pytest.raises(RemoteConfigUnavailableError) as exc_info:
            RemoteConfigFetcher.fetch_remote_config(require_fresh=True)

        assert "was refused because a fresh fetch is required" in str(exc_info.value)

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_inner_retry_layer_still_raises_remote_config_fetch_error(self, mocker: MockerFixture) -> None:
        """Internal retry layer keeps raising ``RemoteConfigFetchError``; the outer flow turns it
        into a cache hit or an unavailable error. Callers that introspect the inner exception
        (doctor, error handlers, agent hints) still see the original class.
        """
        mocker.patch("httpx.get", side_effect=httpx.ConnectError("no network"))
        mocker.patch.object(RemoteConfigFetcher, "FETCH_MAX_RETRIES", 1)

        with pytest.raises(RemoteConfigUnavailableError) as exc_info:
            RemoteConfigFetcher.fetch_remote_config()

        cause = exc_info.value.__cause__
        assert isinstance(cause, RemoteConfigFetchError), (
            "RemoteConfigUnavailableError must chain from the original RemoteConfigFetchError "
            "so existing surfaces (doctor, agent hints) can keep reading the inner exception"
        )

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_cache_store_oserror_does_not_abort_fresh_fetch(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Cache write is opportunistic — a read-only ``$HOME``, full disk, or permission
        error on the cache directory must not kill an otherwise-successful online fetch.
        ``fetch_remote_config`` should warn to stderr and still return ``source=FRESH``.
        """
        payload = _valid_remote_config_payload()
        mocker.patch("httpx.get", return_value=_make_httpx_response(payload))
        mocker.patch.object(RemoteConfigCache, "store", side_effect=OSError("read-only filesystem"))

        result = RemoteConfigFetcher.fetch_remote_config()

        assert result.source == RemoteConfigSource.FRESH
        assert result.config.aws_region == "eu-west-3"
        captured = capsys.readouterr()
        assert "failed to persist remote config cache" in captured.err, (
            f"cache-write failure must surface as a warning on stderr; got stderr={captured.err!r}"
        )

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_fresh_path_validates_payload_only_once(self, mocker: MockerFixture) -> None:
        """``_fetch_fresh`` already validates the payload; the outer flow must reuse the
        parsed config rather than re-validating it. We spy on ``RemoteConfig.model_validate``
        and assert it was called exactly once for a fresh fetch.
        """
        payload = _valid_remote_config_payload()
        mocker.patch("httpx.get", return_value=_make_httpx_response(payload))
        validate_spy = mocker.spy(RemoteConfig, "model_validate")

        result = RemoteConfigFetcher.fetch_remote_config()

        assert result.source == RemoteConfigSource.FRESH
        assert validate_spy.call_count == 1, f"fresh path must validate exactly once; got {validate_spy.call_count} calls"
