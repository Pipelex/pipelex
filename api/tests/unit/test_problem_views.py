"""The view of a problem a response carries follows the identity the request's authentication established.

The operator, whoever runs this runner, reads the operator view, with `diagnostics`, the operator's next step and the
operator-only parameters; anyone else reads the caller view. The real authentication dependencies of
`pipelex_api.security` pick it here, each with synthetic credentials patched into the environment:

- `AUTH_MODE=api_key`: the static API key is the operator's own credential, so `verify_api_key` marks the request.
- `AUTH_MODE=none` with `TRUST_FORWARDED_IDENTITY_HEADERS=true`: `no_auth` marks a request the trusted proxy forwarded.
- `AUTH_MODE=jwt`, whose token names a caller, plain `AUTH_MODE=none`, and a request refused before any authentication
  ran read the caller view.

Every problem document the server emits, in either view, also holds no member written as `null`, at any depth.
"""

import os
from enum import StrEnum
from typing import Any, cast

import jwt
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexConfigError, PipelexError
from pipelex.errors.problem import PipelexProblem, ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.mthds_parsing.parser import MthdsParser
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.middleware import RequestIdMiddleware
from pipelex_api.problem_view import mark_operator_request
from pipelex_api.security import ForwardedIdentityHeader, no_auth, verify_api_key, verify_jwt
from tests.unit.test_data import ProblemTestData, rate_limited_failure

_GATEWAY_CONFIG_MESSAGE = "the gateway config is missing"
_COMPONENT = "pipe_func_sandbox"
_TRUST_FORWARDED = "TRUST_FORWARDED_IDENTITY_HEADERS"


class _Identity(StrEnum):
    """The identity a request authenticates as, one per authentication mode and trust setting."""

    API_KEY = "api_key"
    FORWARDED_IDENTITY = "forwarded_identity"
    JWT = "jwt"
    NO_AUTH = "no_auth"


# Each identity's dependency, the environment it reads, and the view its requests read.
_IDENTITIES: dict[_Identity, tuple[Any, dict[str, str], ProblemView]] = {
    _Identity.API_KEY: (verify_api_key, {"API_KEY": ProblemTestData.SYNTHETIC_API_KEY}, ProblemView.OPERATOR),
    _Identity.FORWARDED_IDENTITY: (no_auth, {_TRUST_FORWARDED: "true"}, ProblemView.OPERATOR),
    _Identity.JWT: (verify_jwt, {"JWT_SECRET_KEY": ProblemTestData.SYNTHETIC_JWT_SECRET}, ProblemView.CALLER),
    _Identity.NO_AUTH: (no_auth, {}, ProblemView.CALLER),
}


class _MisconfiguredComponentError(PipelexError):
    """A deployment's misconfigured component, whose name `runtime.misconfigured` declares an operator-only parameter."""

    error_code = CoreCode.RUNTIME_MISCONFIGURED


class _RecoveredProblemError(PipelexError):
    """Carries a problem recovered across a transport boundary in the operator's view, which it reports as it is."""

    def __init__(self, message: str, *, problem: PipelexProblem):
        super().__init__(message)
        self.carried_problem = problem

    @override
    def recovered_problem(self) -> PipelexProblem | None:
        return self.carried_problem


# Route handlers are deliberately not underscore-prefixed: a private,
# decorator-only function reads as unused to the type checker.
_router = APIRouter()


@_router.get("/config-error")
async def config_error_route() -> None:
    raise PipelexConfigError(_GATEWAY_CONFIG_MESSAGE)


@_router.get("/misconfigured")
async def misconfigured_route() -> None:
    msg = "the PipeFunc sandbox states no package set"
    raise _MisconfiguredComponentError(msg).with_params(component=_COMPONENT)


@_router.get("/llm-error")
async def llm_error_route() -> None:
    raise rate_limited_failure()


@_router.get("/invalid-method")
async def invalid_method_route() -> None:
    MthdsParser.make_pipelex_bundle_blueprint(mthds_content="this is not TOML !!!", mthds_source="bad.mthds")


@_router.get("/unexpected-error")
async def unexpected_error_route() -> None:
    msg = "something nobody anticipated"
    raise RuntimeError(msg)


@_router.get("/unknown-code")
async def unknown_code_route() -> None:
    msg = "a worker reported a code this server does not know"
    raise _RecoveredProblemError(msg, problem=PipelexProblem.model_validate(ProblemTestData.UNKNOWN_OPERATOR_PROBLEM))


async def refuse_before_authentication() -> None:
    """A refusal that runs before the authentication dependency, so nothing has marked the request yet."""
    raise PipelexConfigError(_GATEWAY_CONFIG_MESSAGE)


def _authenticated_client(mocker: MockerFixture, *, identity: _Identity, refuse_first: bool = False) -> tuple[TestClient, dict[str, str]]:
    """An app behind `identity`'s real dependency, with its synthetic environment, and the headers its credential travels in."""
    dependency, environment, _ = _IDENTITIES[identity]
    mocker.patch.dict(os.environ, environment)
    if _TRUST_FORWARDED not in environment:
        os.environ.pop(_TRUST_FORWARDED, None)
    headers: dict[str, str]
    match identity:
        case _Identity.API_KEY:
            headers = {"Authorization": f"Bearer {ProblemTestData.SYNTHETIC_API_KEY}"}
        case _Identity.FORWARDED_IDENTITY:
            headers = {ForwardedIdentityHeader.USER_ID: ProblemTestData.FORWARDED_USER_ID}
        case _Identity.JWT:
            token = jwt.encode({"user_id": ProblemTestData.JWT_USER_ID}, ProblemTestData.SYNTHETIC_JWT_SECRET, algorithm="HS256")
            headers = {"Authorization": f"Bearer {token}"}
        case _Identity.NO_AUTH:
            headers = {}
    dependencies = [Depends(refuse_before_authentication)] if refuse_first else []
    dependencies.append(Depends(dependency))
    app = FastAPI()
    app.include_router(_router, dependencies=dependencies)
    register_exception_handlers(app)
    return TestClient(app), headers


def _marked_client(*, view: ProblemView) -> TestClient:
    """An app whose requests read `view`, marked as the authentication would, behind the request-id middleware."""
    app = FastAPI()
    match view:
        case ProblemView.OPERATOR:
            app.include_router(_router, dependencies=[Depends(mark_operator_request)])
        case ProblemView.CALLER:
            app.include_router(_router)
    register_exception_handlers(app)
    return TestClient(RequestIdMiddleware(app), raise_server_exceptions=False)


def _null_paths(value: Any, *, path: str) -> list[str]:
    """The path of every member of `value`, at any depth, written as `null`."""
    if value is None:
        return [path]
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in cast("dict[str, Any]", value).items():
            found.extend(_null_paths(item, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(cast("list[Any]", value)):
            found.extend(_null_paths(item, path=f"{path}[{index}]"))
    return found


class TestProblemViews:
    @pytest.mark.parametrize("identity", list(_IDENTITIES))
    def test_the_view_follows_the_identity(self, mocker: MockerFixture, identity: _Identity) -> None:
        """An operator's fault: the operator reads its message and fixes the configuration, a caller reports it."""
        _, _, expected_view = _IDENTITIES[identity]
        client, headers = _authenticated_client(mocker, identity=identity)

        response = client.get("/config-error", headers=headers)

        assert response.status_code == 500
        body = response.json()
        assert body["code"] == PipelexErrorCode.CONFIG_INVALID
        assert body["domain"] == "operator"
        match expected_view:
            case ProblemView.OPERATOR:
                assert body["next_step"]["kind"] == "fix_configuration"
                assert body["diagnostics"]["error_class"] == "PipelexConfigError"
                assert body["diagnostics"]["message"] == _GATEWAY_CONFIG_MESSAGE
            case ProblemView.CALLER:
                assert body["next_step"]["kind"] == "report"
                assert "diagnostics" not in body
                assert _GATEWAY_CONFIG_MESSAGE not in response.text

    @pytest.mark.parametrize("identity", list(_IDENTITIES))
    def test_operator_only_params_ride_the_operator_view_alone(self, mocker: MockerFixture, identity: _Identity) -> None:
        _, _, expected_view = _IDENTITIES[identity]
        client, headers = _authenticated_client(mocker, identity=identity)

        response = client.get("/misconfigured", headers=headers)

        assert response.status_code == 500
        body = response.json()
        assert body["code"] == CoreCode.RUNTIME_MISCONFIGURED
        # The parameter is the operator's alone: never among the caller-visible `params`, whoever reads.
        assert "params" not in body
        match expected_view:
            case ProblemView.OPERATOR:
                assert body["diagnostics"]["params"] == {"component": _COMPONENT}
            case ProblemView.CALLER:
                assert "diagnostics" not in body
                assert _COMPONENT not in response.text

    def test_a_request_refused_before_authentication_reads_the_caller_view(self, mocker: MockerFixture) -> None:
        """The operator's own key, presented on a request refused before the key was checked, still reads the caller view."""
        client, headers = _authenticated_client(mocker, identity=_Identity.API_KEY, refuse_first=True)

        response = client.get("/config-error", headers=headers)

        assert response.status_code == 500
        body = response.json()
        assert body["code"] == PipelexErrorCode.CONFIG_INVALID
        assert body["next_step"]["kind"] == "report"
        assert "diagnostics" not in body
        assert _GATEWAY_CONFIG_MESSAGE not in response.text

    def test_a_refused_credential_marks_nothing(self, mocker: MockerFixture) -> None:
        """A wrong API key is refused with the API's own 401, which carries no diagnostics, and never reaches the route."""
        client, _ = _authenticated_client(mocker, identity=_Identity.API_KEY)

        response = client.get("/config-error", headers={"Authorization": "Bearer not-the-configured-key"})

        assert response.status_code == 401
        body = response.json()
        assert body["error_type"] == "InvalidToken"
        assert "diagnostics" not in body
        assert "code" not in body

    @pytest.mark.parametrize("identity", list(_IDENTITIES))
    def test_an_unknown_code_reaches_a_caller_without_the_operator_step(self, mocker: MockerFixture, identity: _Identity) -> None:
        """A recorded problem whose code this server does not know: its caller reads a generic step, never the operator's."""
        _, _, expected_view = _IDENTITIES[identity]
        client, headers = _authenticated_client(mocker, identity=identity)

        response = client.get("/unknown-code", headers=headers)

        assert response.status_code == 500
        body = response.json()
        assert body["code"] == ProblemTestData.UNKNOWN_OPERATOR_PROBLEM["code"]
        match expected_view:
            case ProblemView.OPERATOR:
                assert body["next_step"] == ProblemTestData.UNKNOWN_OPERATOR_PROBLEM["next_step"]
                assert body["diagnostics"]["error_class"] == "FutureSettingError"
            case ProblemView.CALLER:
                assert body["next_step"] == {"kind": "report", "detail": "Report this problem with its request id."}
                assert "diagnostics" not in body
                assert ProblemTestData.PRIVATE_HOST_FILE not in response.text

    @pytest.mark.parametrize("view", [ProblemView.OPERATOR, ProblemView.CALLER])
    @pytest.mark.parametrize("path", ["/config-error", "/misconfigured", "/llm-error", "/invalid-method", "/unexpected-error"])
    def test_no_problem_document_holds_a_null_member(self, view: ProblemView, path: str) -> None:
        response = _marked_client(view=view).get(path)

        assert response.status_code >= 400
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["code"]
        assert _null_paths(body, path="$") == []
