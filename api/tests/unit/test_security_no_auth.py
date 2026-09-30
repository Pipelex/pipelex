from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pipelex.system.storage_scope import SINGLE_TENANT_USER_ID
from pytest_mock import MockerFixture

from api.exception_handlers import register_exception_handlers
from api.security import ForwardedIdentityHeader, RequestUser, get_request_user, no_auth
from tests.unit._constants import RoutePath

USER_ID = "11111111-1111-4111-1111-111111111111"


async def _whoami(user: Annotated[RequestUser | None, Depends(get_request_user)]) -> dict[str, str | None]:
    if user is None:
        return {"user_id": None}
    return {"user_id": user.user_id}


def _build_client() -> TestClient:
    app = FastAPI()
    app.add_api_route(RoutePath.WHOAMI, _whoami, methods=["GET"], dependencies=[Depends(no_auth)])
    register_exception_handlers(app)
    return TestClient(app)


class TestNoAuthForwardedHeaders:
    def test_header_ignored_by_default(self, mocker: MockerFixture):
        """No TRUST_FORWARDED_IDENTITY_HEADERS env → X-User-Id is not trusted."""
        mocker.patch("api.security.get_optional_env", return_value=None)
        client = _build_client()
        headers: dict[str, str] = {ForwardedIdentityHeader.USER_ID: USER_ID}
        response = client.get(RoutePath.WHOAMI, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"user_id": None}

    def test_header_ignored_when_flag_not_true(self, mocker: MockerFixture):
        mocker.patch("api.security.get_optional_env", return_value="false")
        client = _build_client()
        headers: dict[str, str] = {ForwardedIdentityHeader.USER_ID: USER_ID}
        response = client.get(RoutePath.WHOAMI, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"user_id": None}

    def test_user_id_honored_when_flag_true(self, mocker: MockerFixture):
        """With the trust flag enabled, the runner reads X-User-Id and only that."""
        mocker.patch("api.security.get_optional_env", return_value="true")
        client = _build_client()
        # Extra X-User-* headers are noise — the runner ignores them by design.
        headers: dict[str, str] = {
            ForwardedIdentityHeader.USER_ID: USER_ID,
            "x-user-email": "evil@example.com",
            "x-user-sub": "spoofed#1",
            "x-auth-method": "gateway",
        }
        response = client.get(RoutePath.WHOAMI, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"user_id": USER_ID}

    @pytest.mark.parametrize("user_id", ["", None])
    def test_a_missing_forwarded_user_id_is_rejected(self, mocker: MockerFixture, user_id: str | None):
        """**This used to stay anonymous, and that was the bug.**

        Turning `TRUST_FORWARDED_IDENTITY_HEADERS` on is a deployment asserting
        "a proxy in front of me authenticates every caller". A request arriving
        without the header therefore means that proxy is absent, misconfigured
        or bypassed — and the old behaviour was to continue under a shared
        owner, which put every caller of a multi-tenant server into one storage
        namespace where each could read the others' outputs. It looked like a
        working request the whole way through.

        There is no `anonymous` sentinel any more: an empty header and an absent
        one are the same failure, and both are 401.
        """
        mocker.patch("api.security.get_optional_env", return_value="true")
        client = _build_client()
        headers: dict[str, str] = {} if user_id is None else {ForwardedIdentityHeader.USER_ID: user_id}
        response = client.get(RoutePath.WHOAMI, headers=headers)
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"

    def test_the_reserved_single_tenant_id_is_not_special_on_the_wire(self, mocker: MockerFixture):
        """`single-tenant` forwarded by a proxy is an ordinary path-safe id here.

        The reservation is enforced where it matters — `verify_jwt` refuses a
        token claiming it — not by giving the string a second meaning on the
        forwarded path. A proxy that genuinely wants to forward it is asserting
        an identity, which is what this flag means.
        """
        mocker.patch("api.security.get_optional_env", return_value="true")
        client = _build_client()
        headers: dict[str, str] = {ForwardedIdentityHeader.USER_ID: SINGLE_TENANT_USER_ID}
        response = client.get(RoutePath.WHOAMI, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"user_id": SINGLE_TENANT_USER_ID}

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
    def test_path_unsafe_forwarded_user_id_rejected(self, mocker: MockerFixture, unsafe_user_id: str):
        r"""A forwarded `X-User-Id` that is not a single path-safe segment fails closed.

        `user_id` is the owner segment of every storage key, so a value
        containing `/`, `\`, control chars, or being `.`/`..` could enable
        traversal. The proxy intended to authenticate someone but forwarded a
        malformed value — we reject the request (400) rather than silently
        downgrade to a shared owner and scope the caller's outputs into someone
        else's namespace.
        """
        mocker.patch("api.security.get_optional_env", return_value="true")
        client = _build_client()
        headers: dict[str, str] = {ForwardedIdentityHeader.USER_ID: unsafe_user_id}
        response = client.get(RoutePath.WHOAMI, headers=headers)
        assert response.status_code == 400
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "BadRequest"

    @pytest.mark.parametrize(
        "opaque_user_id",
        [
            "user-123",
            "user_11111111-1111-4111-8111-111111111111",  # the prefixed id scheme
            "a" * 36,
        ],
    )
    def test_opaque_forwarded_user_id_honored(self, mocker: MockerFixture, opaque_user_id: str):
        """The runner treats `user_id` as opaque — any path-safe value is honored.

        Identity is enforced upstream (the trusted proxy / gateway injects the
        authenticated id); the runner only requires path-safety, so a non-UUID
        but safe id (incl. the `user_<uuid>` prefixed scheme) is used as-is.
        """
        mocker.patch("api.security.get_optional_env", return_value="true")
        client = _build_client()
        headers: dict[str, str] = {ForwardedIdentityHeader.USER_ID: opaque_user_id}
        response = client.get(RoutePath.WHOAMI, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"user_id": opaque_user_id}
