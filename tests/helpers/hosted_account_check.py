"""Whether the hosted end-to-end cases may start: the key they hold, the origin they call and the account it acts for.

The hosted cases spend credit as one registered test account, which the Pipelex team's `test-account run` hands over in
`PIPELEX_API_KEY`, with `PIPELEX_BASE_URL` naming the dev plane and, beside the key, what the account should be
(`Expectation`): `PIPELEX_API_KEY_EXPECTED_ORG_ID`, `PIPELEX_API_KEY_EXPECTED_ROLE` and `PIPELEX_API_KEY_EXPECTED_EMAIL`.
Before the first case, `require_hosted_account` checks, in this order:

1. that no variable the cases read was replaced by a `.env` file, since pipelex loads `~/.pipelex/.env` and the working
   directory's `.env` over the environment it was started with, so a key saved there would silently replace the one
   handed over (`pipelex.system.environment.get_dotenv_source`);
2. that the origin is not the production API, unless `PIPELEX_HOSTED_E2E_ALLOW_PRODUCTION=1` asks for it, since the cases
   fall back to it when `PIPELEX_BASE_URL` is unset;
3. that the three expectations are set;
4. that `GET /v1/me`, asked with the key, states the expected organization, role and email.

Nothing is sent until the first three hold. Any finding stops the whole session once, with every finding, each naming
the variable, the value found and the value expected. A platform whose `/v1/me` predates its `organization` member is
reported as such and stops the session too, never as a pass. The page for a person is `DOC`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol, cast
from urllib.parse import urlsplit

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from pipelex.hosted.client_factory import HOSTED_API_DEFAULT_BASE_URL, PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY, redact_url_for_display
from pipelex.system.environment import get_dotenv_source
from pipelex.tools.misc.placeholder import value_is_placeholder

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

#: The page that says where the hosted cases' account comes from and how this check reads it.
DOC = "docs/contribute/hosted-end-to-end-tests.md"
#: The variable that lets the hosted cases run against the production API, when it holds exactly `1`.
ALLOW_PRODUCTION_ENV_KEY = "PIPELEX_HOSTED_E2E_ALLOW_PRODUCTION"
ALLOW_PRODUCTION_VALUE = "1"
#: The production API, where the hosted cases go when `PIPELEX_BASE_URL` is unset.
PRODUCTION_BASE_URL = HOSTED_API_DEFAULT_BASE_URL
ME_PATH = "/v1/me"
ME_TIMEOUT_SECONDS = 30.0
#: The statuses by which the platform refuses the key itself.
KEY_REFUSAL_STATUSES = frozenset({401, 403})
#: How the Pipelex team hands the cases their account; the consumer's name is the one the test-account registry declares.
TEST_ACCOUNT_RUN_COMMAND = "test-account run pipelex-hosted-e2e -- .venv/bin/pytest -m pipelex_api tests/e2e/pipelex/cli/test_hosted_run_cli.py"


class Expectation(StrEnum):
    """What the test-account registry expects of a key, each in the variable named after the key's with this suffix."""

    ORG_ID = "_EXPECTED_ORG_ID"
    ROLE = "_EXPECTED_ROLE"
    EMAIL = "_EXPECTED_EMAIL"

    def variable_for(self, *, key_env: str) -> str:
        """The variable holding this expectation of the key in the variable `key_env`."""
        return f"{key_env}{self}"


class ExpectedAccount(BaseModel):
    """What the environment says the key in `key_env` should be."""

    model_config = ConfigDict(frozen=True)

    key_env: str
    org_id: str
    role: str
    email: str


class MeAnswer(NamedTuple):
    """What `GET /v1/me` answered: its status and its JSON body, or why no answer came."""

    status_code: int | None
    body: object
    #: Why there is no answer to read, the request having failed; `None` when the platform answered.
    failure: str | None = None


class Finding(NamedTuple):
    """One reason the hosted cases may not start."""

    message: str
    #: Whether the account itself differs from the registry, which only the registry's owner restores.
    owner_restores: bool = False


class MeFetcher(Protocol):
    def __call__(self, *, base_url: str, api_key: str) -> MeAnswer: ...


def checked_env_vars(*, key_env: str) -> list[str]:
    """Every variable the hosted cases read, each of which must come from the process environment and not a `.env` file."""
    return [key_env, PIPELEX_BASE_URL_ENV_KEY, *(expectation.variable_for(key_env=key_env) for expectation in Expectation), ALLOW_PRODUCTION_ENV_KEY]


def dotenv_findings(*, dotenv_sources: Mapping[str, Path]) -> list[Finding]:
    """A finding per variable a `.env` file set over the process environment, naming the file."""
    return [
        Finding(
            message=(
                f"{env_var} holds the value {dotenv_path} sets, which pipelex loads over the environment it was started with, "
                f"so the value handed over is not the one in use: remove {env_var} from that file, or run from a directory, "
                "and with a PIPELEX_HOME, whose `.env` does not set it"
            )
        )
        for env_var, dotenv_path in dotenv_sources.items()
    ]


def _host_of(url: str) -> str | None:
    """The URL's host, lowercased by `urlsplit` and without the root's trailing dot, which names the same host in DNS."""
    hostname = urlsplit(url.strip()).hostname
    return hostname.removesuffix(".") if hostname else hostname


def is_production(*, base_url: str) -> bool:
    """Whether the origin is the production API's host, whatever its scheme, port, case or trailing dot."""
    return _host_of(base_url) == _host_of(PRODUCTION_BASE_URL)


def production_finding(*, base_url: str | None, environ: Mapping[str, str]) -> Finding | None:
    """The finding refusing the production API, unless `ALLOW_PRODUCTION_ENV_KEY` asks for it; `None` for any other origin."""
    if environ.get(ALLOW_PRODUCTION_ENV_KEY) == ALLOW_PRODUCTION_VALUE:
        return None
    if base_url and not is_production(base_url=base_url):
        return None
    origin = (
        f"{PIPELEX_BASE_URL_ENV_KEY} names the production API ({redact_url_for_display(url=base_url)})"
        if base_url
        else f"{PIPELEX_BASE_URL_ENV_KEY} is not set, so the cases would run on the production API ({PRODUCTION_BASE_URL})"
    )
    return Finding(
        message=(
            f"{origin}: set {PIPELEX_BASE_URL_ENV_KEY} to the plane the key belongs to, "
            f"or set {ALLOW_PRODUCTION_ENV_KEY}={ALLOW_PRODUCTION_VALUE} to run on production on purpose"
        )
    )


def missing_expectations(*, key_env: str, environ: Mapping[str, str]) -> list[str]:
    """The expectation variables of the key in `key_env` that the environment leaves unset or empty."""
    return [expectation.variable_for(key_env=key_env) for expectation in Expectation if not environ.get(expectation.variable_for(key_env=key_env))]


def expected_account(*, key_env: str, environ: Mapping[str, str]) -> ExpectedAccount:
    """The account the environment expects the key in `key_env` to be; every expectation must be set (`missing_expectations`)."""
    return ExpectedAccount(
        key_env=key_env,
        org_id=environ[Expectation.ORG_ID.variable_for(key_env=key_env)],
        role=environ[Expectation.ROLE.variable_for(key_env=key_env)],
        email=environ[Expectation.EMAIL.variable_for(key_env=key_env)],
    )


def _organization_label(organization: Mapping[str, Any]) -> str:
    """An organization as a finding names it: its name and its id, or its id alone when it states no name."""
    name = organization.get("name")
    org_id = organization.get("org_id")
    return f"{name} ({org_id})" if isinstance(name, str) and name else f"{org_id}"


def _problem_code(body: object) -> str | None:
    if isinstance(body, dict):
        code = cast("dict[str, Any]", body).get("code")
        if isinstance(code, str):
            return code
    return None


def read_me_answer(*, answer: MeAnswer, expected: ExpectedAccount, base_url: str) -> list[Finding]:
    """Compare what `/v1/me` stated about the key with what the environment expects of it.

    The email is compared ignoring case, the organization by its id and the role exactly. An answer without the
    `organization` member comes from a platform that predates it: it is reported as that, never as a pass.
    """
    key_env = expected.key_env
    shown_base_url = redact_url_for_display(url=base_url)
    if answer.failure is not None:
        return [Finding(message=f"{key_env}: `{ME_PATH}` at {shown_base_url} could not be asked: {answer.failure}")]
    body = answer.body
    if answer.status_code != 200 or not isinstance(body, dict):
        code = _problem_code(body)
        status = f"HTTP {answer.status_code}" + (f" {code}" if code else "")
        if answer.status_code in KEY_REFUSAL_STATUSES:
            return [Finding(message=f"{key_env}: `{ME_PATH}` at {shown_base_url} refused the key ({status})", owner_restores=True)]
        return [Finding(message=f"{key_env}: `{ME_PATH}` at {shown_base_url} answered {status}, not the account the key belongs to")]
    profile = cast("dict[str, Any]", body)
    findings: list[Finding] = []
    email = profile.get("email")
    if not isinstance(email, str) or email.casefold() != expected.email.casefold():
        variable = Expectation.EMAIL.variable_for(key_env=key_env)
        findings.append(
            Finding(message=f"{key_env}: `{ME_PATH}` states the account {email!r}, where {variable} expects {expected.email!r}", owner_restores=True)
        )
    if "organization" not in profile:
        findings.append(
            Finding(
                message=(
                    f"{key_env}: the platform does not state the key's organization yet, so its organization and role cannot be compared "
                    f"with {Expectation.ORG_ID.variable_for(key_env=key_env)} and {Expectation.ROLE.variable_for(key_env=key_env)}"
                )
            )
        )
        return findings
    organization = profile["organization"]
    if not isinstance(organization, dict):
        variable = Expectation.ORG_ID.variable_for(key_env=key_env)
        findings.append(
            Finding(
                message=f"{key_env}: `{ME_PATH}` states the key acts for no organization, where {variable} expects {expected.org_id!r}",
                owner_restores=True,
            )
        )
        return findings
    stated = cast("dict[str, Any]", organization)
    if stated.get("org_id") != expected.org_id:
        variable = Expectation.ORG_ID.variable_for(key_env=key_env)
        findings.append(
            Finding(
                message=f"{key_env}: `{ME_PATH}` states the organization {_organization_label(stated)}, where {variable} expects {expected.org_id!r}",
                owner_restores=True,
            )
        )
    if stated.get("role_in_org") != expected.role:
        variable = Expectation.ROLE.variable_for(key_env=key_env)
        findings.append(
            Finding(
                message=(
                    f"{key_env}: `{ME_PATH}` states the role {stated.get('role_in_org')!r} in {_organization_label(stated)}, "
                    f"where {variable} expects {expected.role!r}"
                ),
                owner_restores=True,
            )
        )
    return findings


def fetch_me(*, base_url: str, api_key: str, transport: httpx.BaseTransport | None = None) -> MeAnswer:
    """Ask `GET /v1/me` who the key is, with the key as the bearer token of this one request.

    Args:
        base_url: The origin to ask, `scheme://host[:port]`.
        api_key: The key; it is sent and never shown.
        transport: The transport to send through, for a test; `None` sends over the network.

    Returns:
        The status and the JSON body, `None` for a body that is not JSON, or why the request failed.
    """
    url = f"{base_url.strip().rstrip('/')}{ME_PATH}"
    try:
        with httpx.Client(transport=transport, timeout=ME_TIMEOUT_SECONDS) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        # The exception's text may quote the URL, which this message shows redacted instead.
        return MeAnswer(status_code=None, body=None, failure=f"the request failed ({type(exc).__name__})")
    try:
        body: object = response.json()
    except ValueError:
        body = None
    return MeAnswer(status_code=response.status_code, body=body)


def hosted_account_findings(
    *,
    environ: Mapping[str, str],
    dotenv_sources: Mapping[str, Path],
    fetch: MeFetcher,
    key_env: str = PIPELEX_API_KEY_ENV_KEY,
) -> list[Finding]:
    """Every reason the hosted cases may not start, `/v1/me` being asked only once nothing before it stands in the way."""
    findings = dotenv_findings(dotenv_sources=dotenv_sources)
    base_url = environ.get(PIPELEX_BASE_URL_ENV_KEY) or None
    production = production_finding(base_url=base_url, environ=environ)
    if production is not None:
        findings.append(production)
    missing = missing_expectations(key_env=key_env, environ=environ)
    if missing:
        findings.append(
            Finding(
                message=(
                    f"{key_env}: {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set, so the account the key acts for "
                    "cannot be checked: hand the key over with `test-account run`, which sets them beside it"
                )
            )
        )
    api_key = environ.get(key_env)
    if not api_key and key_env not in dotenv_sources:
        findings.append(Finding(message=f"{key_env} is not set"))
    if findings or not api_key:
        return findings
    origin = base_url or PRODUCTION_BASE_URL
    return read_me_answer(
        answer=fetch(base_url=origin, api_key=api_key), expected=expected_account(key_env=key_env, environ=environ), base_url=origin
    )


def stop_message(findings: Sequence[Finding]) -> str:
    """The one message the session stops with when the hosted cases may not start."""
    listed = "\n".join(f"- {finding.message}" for finding in findings)
    owner = (
        "\nAn account, organization or role that differs from the test-account registry is restored by the registry's owner, never by a test."
        if any(finding.owner_restores for finding in findings)
        else ""
    )
    return (
        f"The hosted end-to-end cases did not start:\n{listed}{owner}\n"
        f"The Pipelex team hands them their key with `{TEST_ACCOUNT_RUN_COMMAND}`, which sets {PIPELEX_API_KEY_ENV_KEY}, "
        f"{PIPELEX_BASE_URL_ENV_KEY} and the key's expectations; see {DOC}."
    )


def no_key_handed_over(*, environ: Mapping[str, str], dotenv_sources: Mapping[str, Path], key_env: str = PIPELEX_API_KEY_ENV_KEY) -> bool:
    """Whether the hosted cases are skipped: the key is unset, empty or a placeholder, and no `.env` file set it.

    A key a `.env` file replaced, even with an empty line or a placeholder, is not skipped: the check then names the file,
    where a skip would end a run handed a real key green with nothing run.
    """
    api_key = environ.get(key_env)
    return (not api_key or value_is_placeholder(api_key)) and key_env not in dotenv_sources


def current_dotenv_sources(*, key_env: str = PIPELEX_API_KEY_ENV_KEY) -> dict[str, Path]:
    """The variables the hosted cases read that a `.env` file set when pipelex was imported, with the file that set each."""
    sources: dict[str, Path] = {}
    for env_var in checked_env_vars(key_env=key_env):
        dotenv_path = get_dotenv_source(env_var=env_var)
        if dotenv_path is not None:
            sources[env_var] = dotenv_path
    return sources


def require_hosted_account(*, environ: Mapping[str, str], dotenv_sources: Mapping[str, Path], fetch: MeFetcher = fetch_me) -> None:
    """Stop the whole session once, with every finding, unless the hosted cases hold the key, origin and account handed over."""
    findings = hosted_account_findings(environ=environ, dotenv_sources=dotenv_sources, fetch=fetch)
    if findings:
        pytest.exit(stop_message(findings), returncode=pytest.ExitCode.TESTS_FAILED)
