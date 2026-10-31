from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from tests.helpers.hosted_account_check import (
    ALLOW_PRODUCTION_ENV_KEY,
    MeAnswer,
    current_dotenv_sources,
    fetch_me,
    hosted_account_findings,
    no_key_handed_over,
    require_hosted_account,
    stop_message,
)
from tests.unit.repo.test_data import HostedAccountCheckTestData

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

OWNER_LINE = "is restored by the registry's owner"


class _RecordingFetcher:
    """Answers `/v1/me` with a fixed answer and records every request, so a test can tell whether one was sent."""

    def __init__(self, *, answer: MeAnswer) -> None:
        self.answer = answer
        self.requests: list[tuple[str, str]] = []

    def __call__(self, *, base_url: str, api_key: str) -> MeAnswer:
        self.requests.append((base_url, api_key))
        return self.answer


def _answer(*, body: object, status_code: int = 200) -> _RecordingFetcher:
    return _RecordingFetcher(answer=MeAnswer(status_code=status_code, body=body))


def _me(**changes: Any) -> dict[str, Any]:
    """The matching `/v1/me` body with some members replaced, or removed when given `...`."""
    body: dict[str, Any] = json.loads(json.dumps(HostedAccountCheckTestData.MATCHING_ME))
    for member, value in changes.items():
        if value is ...:
            del body[member]
        else:
            body[member] = value
    return body


def _environ(**changes: str | None) -> dict[str, str]:
    environ = dict(HostedAccountCheckTestData.ENVIRON)
    for name, value in changes.items():
        if value is None:
            environ.pop(name, None)
        else:
            environ[name] = value
    return environ


class TestHostedAccountCheck:
    def test_the_expected_account_passes_with_one_request_to_the_handed_over_origin(self) -> None:
        """The account, organization and role match, the email ignoring case: nothing stands in the way."""
        fetcher = _answer(body=_me(email=HostedAccountCheckTestData.EMAIL.upper()))

        findings = hosted_account_findings(environ=_environ(), dotenv_sources={}, fetch=fetcher)

        assert findings == []
        assert fetcher.requests == [(HostedAccountCheckTestData.DEV_BASE_URL, HostedAccountCheckTestData.API_KEY)]

    @pytest.mark.parametrize(
        ("topic", "body", "expected_fragments"),
        [
            (
                "another organization",
                _me(organization={"org_id": HostedAccountCheckTestData.OTHER_ORG_ID, "name": "QA Lab", "role_in_org": "member"}),
                [
                    f"states the organization QA Lab ({HostedAccountCheckTestData.OTHER_ORG_ID})",
                    f"PIPELEX_API_KEY_EXPECTED_ORG_ID expects '{HostedAccountCheckTestData.ORG_ID}'",
                ],
            ),
            (
                "another role",
                _me(organization={"org_id": HostedAccountCheckTestData.ORG_ID, "name": "QA Runtime", "role_in_org": "runner"}),
                ["states the role 'runner' in QA Runtime", "PIPELEX_API_KEY_EXPECTED_ROLE expects 'member'"],
            ),
            (
                "another account",
                _me(email="someone.else@example.test"),
                ["states the account 'someone.else@example.test'", f"PIPELEX_API_KEY_EXPECTED_EMAIL expects '{HostedAccountCheckTestData.EMAIL}'"],
            ),
            (
                "no organization",
                _me(organization=None),
                ["states the key acts for no organization", f"PIPELEX_API_KEY_EXPECTED_ORG_ID expects '{HostedAccountCheckTestData.ORG_ID}'"],
            ),
        ],
    )
    def test_each_difference_names_the_variable_the_found_value_and_the_expected_one(
        self, topic: str, body: dict[str, Any], expected_fragments: list[str]
    ) -> None:
        """A difference is one finding naming what `/v1/me` stated and what the expectation holds, and its owner restores it."""
        findings = hosted_account_findings(environ=_environ(), dotenv_sources={}, fetch=_answer(body=body))

        assert len(findings) == 1, topic
        assert findings[0].message.startswith("PIPELEX_API_KEY: `/v1/me` ")
        for fragment in expected_fragments:
            assert fragment in findings[0].message
        assert findings[0].owner_restores
        assert OWNER_LINE in stop_message(findings)

    def test_a_platform_without_the_organization_member_is_never_a_pass(self) -> None:
        findings = hosted_account_findings(environ=_environ(), dotenv_sources={}, fetch=_answer(body=_me(organization=..., api_key=...)))

        assert [finding.message for finding in findings] == [
            (
                "PIPELEX_API_KEY: the platform does not state the key's organization yet, so its organization and role cannot be compared "
                "with PIPELEX_API_KEY_EXPECTED_ORG_ID and PIPELEX_API_KEY_EXPECTED_ROLE"
            )
        ]
        assert not findings[0].owner_restores

    @pytest.mark.parametrize(
        ("topic", "missing"),
        [
            ("all three", ["PIPELEX_API_KEY_EXPECTED_ORG_ID", "PIPELEX_API_KEY_EXPECTED_ROLE", "PIPELEX_API_KEY_EXPECTED_EMAIL"]),
            ("one", ["PIPELEX_API_KEY_EXPECTED_ROLE"]),
        ],
    )
    def test_missing_expectations_are_refused_before_any_request(self, topic: str, missing: list[str]) -> None:
        fetcher = _answer(body=_me())

        findings = hosted_account_findings(environ=_environ(**dict.fromkeys(missing)), dotenv_sources={}, fetch=fetcher)

        assert fetcher.requests == [], topic
        assert len(findings) == 1
        assert ", ".join(missing) in findings[0].message
        assert "`test-account run`" in findings[0].message
        assert "test-account run pipelex-hosted-e2e --" in stop_message(findings)

    @pytest.mark.parametrize(
        ("topic", "base_url", "expected_fragment"),
        [
            ("unset", None, "PIPELEX_BASE_URL is not set, so the cases would run on the production API (https://api.pipelex.com)"),
            ("named", "https://API.pipelex.com/", "PIPELEX_BASE_URL names the production API (https://api.pipelex.com/)"),
        ],
    )
    def test_production_is_refused_before_any_request_unless_asked_for(self, topic: str, base_url: str | None, expected_fragment: str) -> None:
        refused_fetcher = _answer(body=_me())

        refused = hosted_account_findings(environ=_environ(PIPELEX_BASE_URL=base_url), dotenv_sources={}, fetch=refused_fetcher)

        assert refused_fetcher.requests == [], topic
        assert len(refused) == 1
        assert expected_fragment in refused[0].message
        assert f"{ALLOW_PRODUCTION_ENV_KEY}=1" in refused[0].message

        allowed_fetcher = _answer(body=_me())
        allowed = hosted_account_findings(
            environ=_environ(PIPELEX_BASE_URL=base_url, **{ALLOW_PRODUCTION_ENV_KEY: "1"}), dotenv_sources={}, fetch=allowed_fetcher
        )

        assert allowed == []
        assert [origin for origin, _ in allowed_fetcher.requests] == [base_url or "https://api.pipelex.com"]

    def test_a_variable_a_dotenv_file_replaced_is_refused_before_any_request(self, tmp_path: Path) -> None:
        """The key in use is not the one handed over, so it is sent nowhere and the file that set it is named."""
        dotenv_path = tmp_path / ".pipelex" / ".env"
        fetcher = _answer(body=_me())

        findings = hosted_account_findings(environ=_environ(), dotenv_sources={"PIPELEX_API_KEY": dotenv_path}, fetch=fetcher)

        assert fetcher.requests == []
        assert len(findings) == 1
        assert findings[0].message.startswith(f"PIPELEX_API_KEY holds the value {dotenv_path} sets, which pipelex loads over the environment")
        assert OWNER_LINE not in stop_message(findings)

    @pytest.mark.parametrize(
        ("topic", "status_code", "body", "expected_fragment", "owner_restores"),
        [
            ("revoked key", 401, {"code": "auth.invalid_credential"}, "refused the key (HTTP 401 auth.invalid_credential)", True),
            ("plane down", 503, None, "answered HTTP 503, not the account the key belongs to", False),
        ],
    )
    def test_an_answer_that_is_not_a_profile_is_a_finding(
        self, topic: str, status_code: int, body: object, expected_fragment: str, owner_restores: bool
    ) -> None:
        findings = hosted_account_findings(environ=_environ(), dotenv_sources={}, fetch=_answer(body=body, status_code=status_code))

        assert len(findings) == 1, topic
        assert expected_fragment in findings[0].message
        assert findings[0].owner_restores is owner_restores

    def test_the_session_stops_once_with_every_finding(self) -> None:
        with pytest.raises(pytest.exit.Exception) as stopped:
            require_hosted_account(
                environ=_environ(PIPELEX_BASE_URL=None, PIPELEX_API_KEY_EXPECTED_EMAIL=None), dotenv_sources={}, fetch=_answer(body=_me())
            )

        assert stopped.value.returncode == pytest.ExitCode.TESTS_FAILED
        message = str(stopped.value.msg)
        assert message.startswith("The hosted end-to-end cases did not start:\n- PIPELEX_BASE_URL is not set")
        assert "\n- PIPELEX_API_KEY: PIPELEX_API_KEY_EXPECTED_EMAIL is not set" in message
        assert HostedAccountCheckTestData.API_KEY not in message

    def test_a_held_account_lets_the_session_go_on(self) -> None:
        require_hosted_account(environ=_environ(), dotenv_sources={}, fetch=_answer(body=_me()))

    def test_fetch_sends_the_key_as_a_bearer_token_to_the_me_route(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=HostedAccountCheckTestData.MATCHING_ME)

        answer = fetch_me(
            base_url=f"{HostedAccountCheckTestData.DEV_BASE_URL}/", api_key=HostedAccountCheckTestData.API_KEY, transport=httpx.MockTransport(handler)
        )

        assert answer == MeAnswer(status_code=200, body=HostedAccountCheckTestData.MATCHING_ME)
        assert [str(request.url) for request in seen] == [f"{HostedAccountCheckTestData.DEV_BASE_URL}/v1/me"]
        assert seen[0].headers["Authorization"] == f"Bearer {HostedAccountCheckTestData.API_KEY}"

    @pytest.mark.parametrize(
        ("topic", "response", "expected"),
        [
            ("not JSON", httpx.Response(502, text="<html>Bad gateway</html>"), MeAnswer(status_code=502, body=None)),
            ("unreachable", None, MeAnswer(status_code=None, body=None, failure="the request failed (ConnectError)")),
        ],
    )
    def test_fetch_reads_what_is_not_a_profile_without_raising(self, topic: str, response: httpx.Response | None, expected: MeAnswer) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if response is None:
                msg = "connection refused"
                raise httpx.ConnectError(msg, request=request)
            return response

        answer = fetch_me(
            base_url=HostedAccountCheckTestData.DEV_BASE_URL, api_key=HostedAccountCheckTestData.API_KEY, transport=httpx.MockTransport(handler)
        )

        assert answer == expected, topic

    @pytest.mark.parametrize(
        ("topic", "api_key", "replaced_by_a_dotenv", "skipped"),
        [
            ("no key", None, False, True),
            ("a placeholder", "placeholder-for-PIPELEX_API_KEY", False, True),
            ("a key", HostedAccountCheckTestData.API_KEY, False, False),
            ("an empty line in a .env over a key", "", True, False),
            ("a placeholder in a .env over a key", "placeholder-for-PIPELEX_API_KEY", True, False),
        ],
    )
    def test_the_cases_are_skipped_only_when_no_key_was_handed_over(
        self, topic: str, api_key: str | None, replaced_by_a_dotenv: bool, skipped: bool, tmp_path: Path
    ) -> None:
        """A key a `.env` replaced, even with nothing, is checked rather than skipped, so the check can name the file."""
        environ = _environ(PIPELEX_API_KEY=api_key)
        dotenv_sources = {"PIPELEX_API_KEY": tmp_path / ".env"} if replaced_by_a_dotenv else {}

        assert no_key_handed_over(environ=environ, dotenv_sources=dotenv_sources) is skipped, topic
        if replaced_by_a_dotenv:
            findings = hosted_account_findings(environ=environ, dotenv_sources=dotenv_sources, fetch=_answer(body=_me()))
            assert [finding.message.split(" holds ")[0] for finding in findings] == ["PIPELEX_API_KEY"]

    def test_the_dotenv_sources_are_read_for_every_variable_the_cases_read(self, tmp_path: Path, mocker: MockerFixture) -> None:
        dotenv_path = tmp_path / ".env"

        def dotenv_source(*, env_var: str) -> Path | None:
            return dotenv_path if env_var in {"PIPELEX_BASE_URL", ALLOW_PRODUCTION_ENV_KEY} else None

        mocker.patch("tests.helpers.hosted_account_check.get_dotenv_source", side_effect=dotenv_source)

        assert current_dotenv_sources() == {"PIPELEX_BASE_URL": dotenv_path, ALLOW_PRODUCTION_ENV_KEY: dotenv_path}
