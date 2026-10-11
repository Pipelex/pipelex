"""Tests for the levels and fields at which api/security logs a refused or unusable credential."""

import logging
from typing import Annotated

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pipelex.system.storage_scope import SINGLE_TENANT_USER_ID
from pipelex.tools.log.log_fields import carried_attributes
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.security import RequestUser, get_request_user, verify_api_key, verify_jwt
from tests.unit._constants import RoutePath

JWT_SECRET = "test-jwt-secret-do-not-use-in-prod"
API_KEY = "test-api-key-static"
USER_ID_UUID = "11111111-1111-4111-1111-111111111111"
SECURITY_LOGGER = "pipelex_api.security"


async def _whoami_jwt(
    _payload: Annotated[dict[str, object], Depends(verify_jwt)],
    user: Annotated[RequestUser | None, Depends(get_request_user)],
) -> dict[str, str | None]:
    if user is None:
        return {"user_id": None}
    return {"user_id": user.user_id}


async def _ping_api_key(_token: Annotated[str, Depends(verify_api_key)]) -> dict[str, str]:
    return {"ok": "yes"}


def _build_jwt_client() -> TestClient:
    app = FastAPI()
    app.add_api_route(RoutePath.WHOAMI, _whoami_jwt, methods=["GET"])
    register_exception_handlers(app)
    return TestClient(app)


def _build_api_key_client() -> TestClient:
    app = FastAPI()
    app.add_api_route(RoutePath.PING, _ping_api_key, methods=["GET"])
    register_exception_handlers(app)
    return TestClient(app)


def _security_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == SECURITY_LOGGER]


class TestSecurityLogLevels:
    """A caller's own credential mistakes log at DEBUG, their reason a field; the server's misconfigurations keep their level.

    The exception handler records every 401 at WARNING with its `error.type` and `detail` already, so a stale client's
    refusals flooded the warnings twice over when the security module warned as well.
    """

    @pytest.mark.parametrize(
        ("client_kind", "secret", "authorization", "expected_mode", "expected_reason"),
        [
            ("jwt", JWT_SECRET, None, "jwt", "missing_bearer_token"),
            ("jwt", JWT_SECRET, "expired", "jwt", "expired_token"),
            ("jwt", JWT_SECRET, "Bearer not.a.real.token", "jwt", "invalid_token"),
            ("api_key", API_KEY, None, "api_key", "missing_bearer_token"),
            ("api_key", API_KEY, "Bearer wrong-key", "api_key", "api_key_mismatch"),
        ],
        ids=["jwt without a token", "an expired jwt", "an invalid jwt", "api key without a token", "a wrong api key"],
    )
    def test_a_callers_refused_credentials_log_at_debug_with_their_reason(
        self,
        *,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
        client_kind: str,
        secret: str,
        authorization: str | None,
        expected_mode: str,
        expected_reason: str,
    ):
        mocker.patch("pipelex_api.security.get_optional_env", return_value=secret)
        client = _build_jwt_client() if client_kind == "jwt" else _build_api_key_client()
        route = RoutePath.WHOAMI if client_kind == "jwt" else RoutePath.PING
        if authorization == "expired":
            authorization = f"Bearer {jwt.encode({'user_id': USER_ID_UUID, 'exp': 0}, JWT_SECRET, algorithm='HS256')}"
        headers = {"Authorization": authorization} if authorization is not None else {}

        with caplog.at_level(logging.DEBUG, logger=SECURITY_LOGGER):
            response = client.get(route, headers=headers)

        assert response.status_code == 401
        (record,) = _security_records(caplog)
        assert record.levelno == logging.DEBUG
        assert record.getMessage() == "A caller's credentials were refused"
        carried = carried_attributes(record=record)
        assert carried["auth_mode"] == expected_mode
        assert carried["auth_refusal_reason"] == expected_reason

    @pytest.mark.parametrize(
        ("client_kind", "expected_env_var"),
        [("jwt", "JWT_SECRET_KEY"), ("api_key", "API_KEY")],
    )
    def test_a_missing_secret_still_logs_at_error_naming_the_variable(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture, client_kind: str, expected_env_var: str
    ):
        mocker.patch("pipelex_api.security.get_optional_env", return_value=None)
        client = _build_jwt_client() if client_kind == "jwt" else _build_api_key_client()
        route = RoutePath.WHOAMI if client_kind == "jwt" else RoutePath.PING

        with caplog.at_level(logging.DEBUG, logger=SECURITY_LOGGER):
            response = client.get(route, headers={"Authorization": "Bearer anything"})

        assert response.status_code == 500
        (record,) = _security_records(caplog)
        assert record.levelno == logging.ERROR
        assert carried_attributes(record=record)["env_var"] == expected_env_var

    @pytest.mark.parametrize(
        "claims",
        [{"iat": 0}, {"user_id": "a/b"}, {"user_id": SINGLE_TENANT_USER_ID}],
        ids=["no user id claim", "an unsafe user id claim", "the single-tenant id"],
    )
    def test_a_verified_token_with_an_unusable_claim_still_warns_the_operator(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture, claims: dict[str, object]
    ):
        """A token that verifies was minted by whoever holds the server's secret, so its unusable claim is the issuer's to fix."""
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        token = jwt.encode(claims, JWT_SECRET, algorithm="HS256")

        with caplog.at_level(logging.DEBUG, logger=SECURITY_LOGGER):
            response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401
        (record,) = _security_records(caplog)
        assert record.levelno == logging.WARNING
        assert "user_action" in carried_attributes(record=record)
