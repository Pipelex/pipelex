from __future__ import annotations

import pytest

from pipelex.hosted.client_factory import (
    HOSTED_API_DEFAULT_BASE_URL,
    PIPELEX_API_KEY_ENV_KEY,
    PIPELEX_BASE_URL_ENV_KEY,
    make_hosted_client,
)
from pipelex.hosted.exceptions import HostedBaseUrlError
from pipelex.tools.misc.package_utils import get_package_version


class TestHostedClientFactory:
    @pytest.fixture(autouse=True)
    def no_hosted_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Start every case with neither variable set, whatever the developer's shell exports."""
        monkeypatch.delenv(PIPELEX_API_KEY_ENV_KEY, raising=False)
        monkeypatch.delenv(PIPELEX_BASE_URL_ENV_KEY, raising=False)

    @pytest.mark.parametrize(
        ("base_url", "env_base_url", "expected"),
        [
            ("https://api-dev.pipelex.com", "https://elsewhere.test", "https://api-dev.pipelex.com"),
            (None, "https://api-dev.pipelex.com", "https://api-dev.pipelex.com"),
            (None, None, HOSTED_API_DEFAULT_BASE_URL),
            ("http://localhost:8081/", None, "http://localhost:8081"),
        ],
    )
    def test_the_base_url_resolves_flag_then_variable_then_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        base_url: str | None,
        env_base_url: str | None,
        expected: str,
    ) -> None:
        """`--base-url` wins over `PIPELEX_BASE_URL`, which wins over the hosted API."""
        if env_base_url is not None:
            monkeypatch.setenv(PIPELEX_BASE_URL_ENV_KEY, env_base_url)
        client = make_hosted_client(base_url=base_url)
        assert client.base_url == expected

    def test_the_default_is_the_hosted_api(self) -> None:
        assert HOSTED_API_DEFAULT_BASE_URL == "https://api.pipelex.com"

    def test_the_key_comes_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The key is the SDK's to resolve: `PIPELEX_API_KEY`, which the runtime loads from `~/.pipelex/.env` at import."""
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_test_not_a_secret")
        assert make_hosted_client().api_key == "plx_sk_test_not_a_secret"

    def test_a_key_given_wins_over_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`pipelex login` checks a key it has not saved yet, whatever `PIPELEX_API_KEY` holds."""
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_the_environment_key")
        assert make_hosted_client(api_key="plx_sk_the_key_to_check").api_key == "plx_sk_the_key_to_check"

    def test_no_key_is_anonymous(self) -> None:
        """No key is not refused here: a self-hosted runner answers its protocol routes without one."""
        assert make_hosted_client().api_key == ""

    def test_the_user_agent_names_pipelex(self) -> None:
        """Every request says it comes from this runtime, so the hosted plane can tell its callers apart."""
        client = make_hosted_client()
        assert client.user_agent.startswith(f"pipelex/{get_package_version()} ")

    @pytest.mark.parametrize(
        ("base_url", "env_base_url", "named_source"),
        [
            ("https://api.pipelex.com/v1", None, "--base-url"),
            ("ftp://api.pipelex.com", None, "--base-url"),
            (None, "https://api.pipelex.com/v1", PIPELEX_BASE_URL_ENV_KEY),
            (None, "", PIPELEX_BASE_URL_ENV_KEY),
        ],
    )
    def test_a_base_url_that_is_not_host_only_is_refused_naming_where_it_came_from(
        self,
        monkeypatch: pytest.MonkeyPatch,
        base_url: str | None,
        env_base_url: str | None,
        named_source: str,
    ) -> None:
        """A path, a query or another scheme is refused before any request, and the message says which setting to fix."""
        if env_base_url is not None:
            monkeypatch.setenv(PIPELEX_BASE_URL_ENV_KEY, env_base_url)
        with pytest.raises(HostedBaseUrlError) as exc_info:
            make_hosted_client(base_url=base_url)
        assert named_source in exc_info.value.message
        assert "scheme://host[:port]" in exc_info.value.message

    @pytest.mark.parametrize(
        ("base_url", "env_base_url"),
        [
            ("https://alice:s3cret-token@api.pipelex.com", None),
            (None, "https://alice:s3cret-token@api.pipelex.com/v1?key=s3cret-token#s3cret-token"),
            ("alice:s3cret-token@api.pipelex.com", None),
            ("https:alice:s3cret-token@api.pipelex.com", None),
            (None, "alice:s3cret-token@api.pipelex.com"),
        ],
    )
    def test_a_refused_base_url_is_echoed_without_its_credentials(
        self, monkeypatch: pytest.MonkeyPatch, base_url: str | None, env_base_url: str | None
    ) -> None:
        """The message is caller-facing and ends up in logs and agent transcripts: the userinfo, query and fragment never reach it."""
        if env_base_url is not None:
            monkeypatch.setenv(PIPELEX_BASE_URL_ENV_KEY, env_base_url)
        with pytest.raises(HostedBaseUrlError) as exc_info:
            make_hosted_client(base_url=base_url)
        message = exc_info.value.message
        assert "s3cret-token" not in message
        assert "alice" not in message
        assert "api.pipelex.com" in message
