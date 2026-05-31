"""Pure read/write/version tests for ``RemoteConfigCache``.

These tests treat the cache as an isolated module: nothing else in the codebase calls it
yet at the time these are written (Phase 1 only stands the cache up; Phase 2 wires it
into ``RemoteConfigFetcher``).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.pipelex_service.remote_config import RemoteConfig
from pipelex.system.pipelex_service.remote_config_cache import (
    CACHE_SCHEMA_VERSION,
    CachedRemoteConfig,
    RemoteConfigCache,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


def _valid_remote_config_payload(extra: dict[str, object] | None = None) -> dict[str, object]:
    """Build a minimal remote-config dict that ``RemoteConfig.model_validate`` accepts."""
    payload: dict[str, object] = {
        "posthog": {
            "project_api_key": "test-key",
            "endpoint": "https://posthog.example.com",
            "is_geoip_enabled": False,
            "is_debug_enabled": False,
        },
        "backend_model_specs": {},
        "aws_region": "eu-west-3",
    }
    if extra is not None:
        payload.update(extra)
    return payload


@pytest.fixture
def isolated_cache_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Point the cache at a fresh tmp ``~/.pipelex`` to keep tests hermetic."""
    fake_global_dir = tmp_path / ".pipelex"
    mocker.patch.object(
        ConfigLoader,
        "global_config_dir",
        new_callable=mocker.PropertyMock,
        return_value=fake_global_dir,
    )
    return fake_global_dir


class TestRemoteConfigCache:
    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_write_then_read_roundtrip(self) -> None:
        payload = _valid_remote_config_payload()

        before_store = datetime.now(tz=timezone.utc)
        RemoteConfigCache.store(payload)
        after_store = datetime.now(tz=timezone.utc)

        loaded = RemoteConfigCache.load()

        assert loaded is not None
        assert isinstance(loaded, CachedRemoteConfig)
        assert loaded.schema_version == CACHE_SCHEMA_VERSION
        assert loaded.raw_config == payload
        assert before_store - timedelta(seconds=1) <= loaded.cached_at <= after_store + timedelta(seconds=1)

        # to_remote_config() must produce a valid RemoteConfig
        remote_config = loaded.to_remote_config()
        assert isinstance(remote_config, RemoteConfig)
        assert remote_config.aws_region == "eu-west-3"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_read_missing_returns_none(self) -> None:
        assert RemoteConfigCache.load() is None

    def test_read_corrupted_json_returns_none_and_logs(
        self,
        isolated_cache_dir: Path,
        mock_log: MagicMock,
    ) -> None:
        cache_path = isolated_cache_dir / "cache" / "remote_config.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("{not valid json", encoding="utf-8")

        assert RemoteConfigCache.load() is None

        assert mock_log.warning.called, "load() must emit a warning when the cache file is unreadable"

    def test_read_wrong_schema_version_returns_none(self, isolated_cache_dir: Path) -> None:
        cache_path = isolated_cache_dir / "cache" / "remote_config.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": CACHE_SCHEMA_VERSION + 99,
                    "cached_at": datetime.now(tz=timezone.utc).isoformat(),
                    "raw_config": _valid_remote_config_payload(),
                }
            ),
            encoding="utf-8",
        )

        assert RemoteConfigCache.load() is None

    def test_write_creates_parent_dir(self, isolated_cache_dir: Path) -> None:
        cache_dir = isolated_cache_dir / "cache"
        assert not cache_dir.exists()

        RemoteConfigCache.store(_valid_remote_config_payload())

        assert cache_dir.is_dir()
        assert (cache_dir / "remote_config.json").is_file()

    def test_cache_path_uses_global_config_dir(self, isolated_cache_dir: Path) -> None:
        expected = isolated_cache_dir / "cache" / "remote_config.json"

        assert RemoteConfigCache.cache_path() == expected

    def test_write_is_atomic(self, isolated_cache_dir: Path, mocker: MockerFixture) -> None:
        """If the atomic rename fails, the destination file must not exist or be corrupted."""
        mocker.patch.object(
            Path,
            "replace",
            side_effect=OSError("simulated replace failure"),
        )

        with pytest.raises(OSError, match="simulated replace failure"):
            RemoteConfigCache.store(_valid_remote_config_payload())

        cache_path = isolated_cache_dir / "cache" / "remote_config.json"
        assert not cache_path.exists(), "destination cache file must not be created when replace fails"

        # No leftover temp files in the cache dir either.
        leftover = list((isolated_cache_dir / "cache").iterdir()) if (isolated_cache_dir / "cache").exists() else []
        assert leftover == [], f"unexpected leftover files in cache dir: {leftover}"

    @pytest.mark.usefixtures("isolated_cache_dir")
    def test_raw_payload_extras_preserved(self) -> None:
        """Unknown top-level keys must round-trip and be preserved on the loaded ``RemoteConfig``."""
        payload = _valid_remote_config_payload(extra={"unknown_future_key": {"hello": "world"}})

        RemoteConfigCache.store(payload)
        loaded = RemoteConfigCache.load()

        assert loaded is not None
        assert loaded.raw_config["unknown_future_key"] == {"hello": "world"}

        remote_config = loaded.to_remote_config()
        # Pydantic ``extra="allow"`` keeps unknown fields accessible via model_extra
        assert remote_config.model_extra == {"unknown_future_key": {"hello": "world"}}
