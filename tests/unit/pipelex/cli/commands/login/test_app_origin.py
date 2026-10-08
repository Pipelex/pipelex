"""`pipelex login` opens the Pipelex app, or the one `PIPELEX_APP_URL` names when it is an origin."""

from __future__ import annotations

import pytest

from pipelex.cli.commands.login.command import PIPELEX_APP_URL_ENV_KEY, build_cli_auth_url, resolve_app_origin
from pipelex.cli.exceptions import PipelexCLIError


class TestAppOrigin:
    def test_the_default_is_the_pipelex_app(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PIPELEX_APP_URL_ENV_KEY, raising=False)
        assert resolve_app_origin() == "https://app.pipelex.com"

    @pytest.mark.parametrize("value", ["https://app-dev.pipelex.com", "https://app-dev.pipelex.com/", "http://localhost:3000"])
    def test_pipelex_app_url_names_another_app(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv(PIPELEX_APP_URL_ENV_KEY, value)
        assert resolve_app_origin() == value.rstrip("/")

    @pytest.mark.parametrize(
        "value", ["", "app.pipelex.com", "ftp://app.test", "https://app.test/auth", "https://user:secret@app.test", "https://app.test?x=1"]
    )
    def test_a_value_that_is_not_an_origin_is_refused_without_quoting_credentials(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv(PIPELEX_APP_URL_ENV_KEY, value)
        with pytest.raises(PipelexCLIError) as exc_info:
            resolve_app_origin()
        assert PIPELEX_APP_URL_ENV_KEY in exc_info.value.message
        assert "secret" not in exc_info.value.message

    def test_the_auth_url_names_the_port_and_the_state(self) -> None:
        url = build_cli_auth_url(app_origin="https://app-dev.pipelex.com", callback_port=51234, state="abc")
        assert url == "https://app-dev.pipelex.com/auth/cli?callback_port=51234&state=abc"
