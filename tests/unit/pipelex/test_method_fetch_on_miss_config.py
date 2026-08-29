"""Unit tests for the fetch-on-miss switch: config default, config override, and env-var precedence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.config import METHODS_FETCH_ON_MISS_ENV_VAR, get_config, is_method_fetch_on_miss_enabled

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestIsMethodFetchOnMissEnabled:
    def test_default_is_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no env override, the shipped config default enables fetch-on-miss."""
        monkeypatch.delenv(METHODS_FETCH_ON_MISS_ENV_VAR, raising=False)
        assert is_method_fetch_on_miss_enabled() is True

    def test_config_can_disable(self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
        """Setting interpreter.methods.fetch_on_miss = false disables fetching."""
        monkeypatch.delenv(METHODS_FETCH_ON_MISS_ENV_VAR, raising=False)
        mocker.patch.object(get_config().interpreter.methods, "fetch_on_miss", False)
        assert is_method_fetch_on_miss_enabled() is False

    @pytest.mark.parametrize("env_value", ["0", "false", "False", "no", "off"])
    def test_env_var_disables(self, monkeypatch: pytest.MonkeyPatch, env_value: str) -> None:
        """A falsy env value disables fetching regardless of the config."""
        monkeypatch.setenv(METHODS_FETCH_ON_MISS_ENV_VAR, env_value)
        assert is_method_fetch_on_miss_enabled() is False

    @pytest.mark.parametrize("env_value", ["1", "true", "True", "yes", "on"])
    def test_env_var_enables(self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, env_value: str) -> None:
        """A truthy env value enables fetching even when the config disables it."""
        monkeypatch.setenv(METHODS_FETCH_ON_MISS_ENV_VAR, env_value)
        mocker.patch.object(get_config().interpreter.methods, "fetch_on_miss", False)
        assert is_method_fetch_on_miss_enabled() is True

    def test_unrecognized_env_value_falls_back_to_config(self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
        """An unparseable env value is ignored in favor of the config."""
        monkeypatch.setenv(METHODS_FETCH_ON_MISS_ENV_VAR, "maybe")
        mocker.patch.object(get_config().interpreter.methods, "fetch_on_miss", False)
        assert is_method_fetch_on_miss_enabled() is False
