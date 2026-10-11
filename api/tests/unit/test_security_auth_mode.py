"""Unit tests for AUTH_MODE resolution: an unset or empty value means `none`, any other value must name a mode."""

import pytest

from pipelex_api.security import AUTH_MODE_ENV_VAR, AuthMode, InvalidAuthModeError, get_auth_dependency, get_auth_mode


class TestAuthMode:
    def test_defaults_to_none_when_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv(AUTH_MODE_ENV_VAR, raising=False)
        assert get_auth_mode() is AuthMode.NONE

    def test_empty_value_defaults_to_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(AUTH_MODE_ENV_VAR, "")
        assert get_auth_mode() is AuthMode.NONE

    @pytest.mark.parametrize("mode", list(AuthMode))
    def test_each_mode_resolves_to_itself(self, monkeypatch: pytest.MonkeyPatch, mode: AuthMode):
        monkeypatch.setenv(AUTH_MODE_ENV_VAR, mode.value)
        assert get_auth_mode() is mode

    @pytest.mark.parametrize("raw", ["jwtt", "apikey", "api-key", "true", "off", " ", " jwt"])
    def test_rejects_unknown_value(self, monkeypatch: pytest.MonkeyPatch, raw: str):
        # An unknown value used to fall back to no authentication, so a typo served every route unauthenticated.
        monkeypatch.setenv(AUTH_MODE_ENV_VAR, raw)
        with pytest.raises(InvalidAuthModeError):
            get_auth_mode()

    @pytest.mark.parametrize("raw", ["JWT", "Api_Key", "NONE"])
    def test_rejects_wrong_case(self, monkeypatch: pytest.MonkeyPatch, raw: str):
        # The match is strict: a value differing from a mode only by case is refused, never folded onto that mode.
        monkeypatch.setenv(AUTH_MODE_ENV_VAR, raw)
        with pytest.raises(InvalidAuthModeError):
            get_auth_mode()

    def test_error_names_the_value_and_every_valid_mode(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(AUTH_MODE_ENV_VAR, "jwtt")
        with pytest.raises(InvalidAuthModeError) as exc_info:
            get_auth_mode()
        message = str(exc_info.value)
        assert "'jwtt'" in message
        for mode in AuthMode:
            assert f"'{mode.value}'" in message

    def test_dependency_selection_refuses_unknown_value(self, monkeypatch: pytest.MonkeyPatch):
        # `pipelex_api.main` selects the dependency at import, so this raise is what stops the server from starting.
        monkeypatch.setenv(AUTH_MODE_ENV_VAR, "jwtt")
        with pytest.raises(InvalidAuthModeError):
            get_auth_dependency()
