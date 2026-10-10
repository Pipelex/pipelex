"""Tests for verify_jwt and verify_api_key in api/security."""

import logging
from typing import Annotated

import jwt
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from pipelex.system.storage_scope import SINGLE_TENANT_USER_ID
from pipelex.system.telemetry.otel_constants import OTelLogAttr
from pipelex.tools.log.log_fields import carried_attributes
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.security import RequestUser, get_request_user, verify_api_key, verify_jwt
from tests.unit._constants import RoutePath

JWT_SECRET = "test-jwt-secret-do-not-use-in-prod"
API_KEY = "test-api-key-static"
USER_ID_UUID = "11111111-1111-4111-1111-111111111111"


async def _whoami_jwt(
    request: Request,
    _payload: Annotated[dict[str, object], Depends(verify_jwt)],
    user: Annotated[RequestUser | None, Depends(get_request_user)],
) -> dict[str, str | None]:
    _ = request
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


class TestSecurityVerifiers:
    def test_jwt_happy_path_user_id_claim(self, mocker: MockerFixture):
        """Preferred claim: explicit `user_id` containing a UUID."""
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        token = jwt.encode({"user_id": USER_ID_UUID}, JWT_SECRET, algorithm="HS256")
        response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == {"user_id": USER_ID_UUID}

    def test_jwt_sub_only_is_rejected(self, mocker: MockerFixture):
        """A JWT with only `sub` (and no `user_id`) is rejected.

        We deliberately do NOT fall back to `sub`: storage URIs require the
        owner segment to be a UUID, and OAuth providers' `sub` values
        (e.g. `"google#abc"`) would let a caller write to S3 keys that
        `/resolve-storage-url` would later refuse to resolve. Deployments
        using OAuth must mint their own `user_id` claim.
        """
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        token = jwt.encode({"sub": "google#abc"}, JWT_SECRET, algorithm="HS256")
        response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "InvalidToken"

    def test_jwt_missing_user_id_claim_rejected(self, mocker: MockerFixture):
        """No `user_id` claim means no caller identifier — reject."""
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        token = jwt.encode({"iat": 0}, JWT_SECRET, algorithm="HS256")
        response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error_type"] == "InvalidToken"

    @pytest.mark.parametrize(
        "unsafe_user_id",
        [
            "../etc/passwd",
            "a/b",
            "..",
            ".",
            "with\x00null",  # C0 control (NUL)
            "with\x7fdel",  # DEL is a control char too — must be rejected
            "google#abc",  # URI fragment delimiter — ambiguous owner segment
            "user@example.com",  # URI userinfo delimiter
            "a:99999",  # URI port delimiter
        ],
    )
    def test_jwt_path_unsafe_user_id_rejected(self, mocker: MockerFixture, unsafe_user_id: str):
        r"""A `user_id` claim that isn't a single path-safe segment is rejected.

        The id becomes the owner segment of every storage key, so a value with
        `/`, `\`, or being `.`/`..` could enable traversal — reject at the auth
        boundary. (Identity/shape is otherwise the issuer's concern; the runner
        treats `user_id` as opaque.)
        """
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        token = jwt.encode({"user_id": unsafe_user_id}, JWT_SECRET, algorithm="HS256")
        response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error_type"] == "InvalidToken"

    @pytest.mark.parametrize(
        ("refused_claim", "expected_claim_type"),
        [
            (42, "int"),
            ({"tenant": "acme"}, "dict"),
            (["acme"], "list"),
            ("../etc/passwd", "str"),
        ],
    )
    def test_a_refused_user_id_claim_is_logged_as_its_type_never_as_user_id(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture, refused_claim: object, expected_claim_type: str
    ):
        """`user.id` names an authenticated caller and is a string on every line; a refused claim is neither.

        The line used to carry the claim as decoded under `user.id`, an integer or an object on some lines, which split
        the field's type, and a value a token issuer put there under a key meaning the caller.
        """
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        token = jwt.encode({"user_id": refused_claim}, JWT_SECRET, algorithm="HS256")

        with caplog.at_level(logging.WARNING):
            response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401
        (record,) = [record for record in caplog.records if record.getMessage() == "A verified token's user id claim is not a path-safe segment"]
        carried = carried_attributes(record=record)
        assert carried.get("claim_type") == expected_claim_type
        assert OTelLogAttr.USER_ID not in carried
        assert refused_claim not in carried.values()

    @pytest.mark.parametrize(
        "opaque_user_id",
        [
            "user-123",
            "user_11111111-1111-4111-8111-111111111111",  # the prefixed id scheme
            "a" * 36,
        ],
    )
    def test_jwt_opaque_user_id_accepted(self, mocker: MockerFixture, opaque_user_id: str):
        """An opaque, path-safe `user_id` claim is accepted as-is (no shape check)."""
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        token = jwt.encode({"user_id": opaque_user_id}, JWT_SECRET, algorithm="HS256")
        response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == {"user_id": opaque_user_id}

    def test_jwt_claiming_the_reserved_single_tenant_id_is_rejected(self, mocker: MockerFixture):
        """A JWT claiming the reserved single-tenant id is rejected.

        The value is path-safe, so it passes the segment check — but it is the
        owner id a deployment with NO user model runs under. An authenticated
        token binding it would land that caller's runs in the single-tenant
        namespace, beside whatever a no-auth deployment of the same image wrote
        there.

        (This case previously guarded the `anonymous` sentinel, which no longer
        exists: identity is required wherever a deployment claims to have one.)
        """
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        token = jwt.encode({"user_id": SINGLE_TENANT_USER_ID}, JWT_SECRET, algorithm="HS256")
        response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error_type"] == "InvalidToken"

    def test_jwt_invalid_token_rejected(self, mocker: MockerFixture):
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        response = client.get(RoutePath.WHOAMI, headers={"Authorization": "Bearer not.a.real.token"})
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error_type"] == "InvalidToken"

    def test_jwt_wrong_secret_rejected(self, mocker: MockerFixture):
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        token = jwt.encode({"user_id": USER_ID_UUID}, "different-secret", algorithm="HS256")
        response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error_type"] == "InvalidToken"

    def test_jwt_missing_secret_returns_500(self, mocker: MockerFixture):
        mocker.patch("pipelex_api.security.get_optional_env", return_value=None)
        client = _build_jwt_client()
        token = jwt.encode({"user_id": USER_ID_UUID}, "anything", algorithm="HS256")
        response = client.get(RoutePath.WHOAMI, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 500
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ServerMisconfigured"

    def test_api_key_happy_path(self, mocker: MockerFixture):
        mocker.patch("pipelex_api.security.get_optional_env", return_value=API_KEY)
        client = _build_api_key_client()
        response = client.get(RoutePath.PING, headers={"Authorization": f"Bearer {API_KEY}"})
        assert response.status_code == 200
        assert response.json() == {"ok": "yes"}

    def test_api_key_wrong_key_rejected(self, mocker: MockerFixture):
        mocker.patch("pipelex_api.security.get_optional_env", return_value=API_KEY)
        client = _build_api_key_client()
        response = client.get(RoutePath.PING, headers={"Authorization": "Bearer wrong-key"})
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error_type"] == "InvalidToken"

    def test_api_key_missing_env_returns_500(self, mocker: MockerFixture):
        mocker.patch("pipelex_api.security.get_optional_env", return_value=None)
        client = _build_api_key_client()
        response = client.get(RoutePath.PING, headers={"Authorization": "Bearer anything"})
        assert response.status_code == 500
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ServerMisconfigured"

    @pytest.mark.parametrize(
        "authorization",
        [
            None,  # header absent
            "",  # header present but empty
            "Bearer",  # bare scheme, no token
            "Basic dXNlcjpwYXNz",  # wrong scheme entirely
        ],
    )
    def test_api_key_missing_or_malformed_header_rejected(self, mocker: MockerFixture, authorization: str | None):
        """Missing / empty / non-Bearer Authorization → RFC 7807 401, not the old shape.

        `HTTPBearer(auto_error=False)` means none of these branches go through
        FastAPI's default `HTTPException` handler (which would emit
        `application/json` `{"detail": "Not authenticated"}`). Instead
        `verify_api_key` sees `credentials is None` and calls
        `raise_unauthenticated(...)` — same problem document as every other 401.
        """
        mocker.patch("pipelex_api.security.get_optional_env", return_value=API_KEY)
        client = _build_api_key_client()
        headers: dict[str, str] = {} if authorization is None else {"Authorization": authorization}
        response = client.get(RoutePath.PING, headers=headers)
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error_type"] == "Unauthenticated"

    @pytest.mark.parametrize(
        "authorization",
        [
            None,
            "",
            "Bearer",
            "Basic dXNlcjpwYXNz",
        ],
    )
    def test_jwt_missing_or_malformed_header_rejected(self, mocker: MockerFixture, authorization: str | None):
        """JWT counterpart of the API-key case: same RFC 7807 401 shape."""
        mocker.patch("pipelex_api.security.get_optional_env", return_value=JWT_SECRET)
        client = _build_jwt_client()
        headers: dict[str, str] = {} if authorization is None else {"Authorization": authorization}
        response = client.get(RoutePath.WHOAMI, headers=headers)
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error_type"] == "Unauthenticated"


SECURITY_LOGGER = "pipelex_api.security"


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
