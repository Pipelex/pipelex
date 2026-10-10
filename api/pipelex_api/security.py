"""Authentication module with configurable AUTH_MODE (none, jwt, api_key).

User identity is extracted during auth and stored on request.state.user as a RequestUser.
Route handlers access it via the get_request_user dependency.
"""

import re
from enum import StrEnum
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pipelex import log
from pipelex.system.environment import get_optional_env
from pipelex.system.storage_scope import SINGLE_TENANT_USER_ID
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.log.log_fields import USER_ACTION_FIELD
from pydantic import BaseModel, Field

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_bad_request, raise_internal_server_error, raise_unauthenticated

# JWT Configuration (only used when AUTH_MODE=jwt)
JWT_ALGORITHM = "HS256"

# A caller's `user_id` is the first path segment of every `pipelex-storage://`
# URI and S3 key (`<user_id>/...`). The runner treats it as an OPAQUE id and
# does NOT validate its identity/shape: a self-hosted deployment may use any id
# scheme (uuid, `user_<uuid>`, …), and a hosted deployment behind a trusted
# proxy receives the *authenticated* id the gateway injects (derived from the
# JWT / API key — never client-chosen). The only constraint is that the id be a
# single, UNAMBIGUOUS path segment, because it is embedded into a
# `pipelex-storage://<user_id>/...` URI / S3 key:
#   - PATH-SAFE: no `/`, `\`, NUL/control chars, DEL; and not `.`/`..` (no traversal).
#   - URI-UNAMBIGUOUS: no URI gen-delims (`:`, `?`, `#`, `[`, `]`, `@`). These
#     parse differently under a raw split vs a standard URI parser — e.g.
#     `pipelex-storage://google#abc/...` has owner `google#abc` by raw split but
#     `google` (with `abc/...` as the fragment) under `urlparse`, so a consumer
#     could resolve a different owner than the one this server authorized.
_PATH_UNSAFE_CHARS = re.compile(r"[/\\:?#\[\]@\x00-\x1f\x7f]")


def is_safe_user_id(value: str) -> bool:
    """True if `value` is usable as a single, path-safe, URI-unambiguous key segment (opaque id)."""
    return bool(value) and value not in (".", "..") and _PATH_UNSAFE_CHARS.search(value) is None


# `SINGLE_TENANT_USER_ID`, imported above from the runtime, is the caller id for
# a deployment that has declared it has NO user model: `AUTH_MODE=none` with
# `TRUST_FORWARDED_IDENTITY_HEADERS` off. Such a server has exactly one tenant by
# configuration, so one namespace is correct rather than accidental.
#
# **This is not the `anonymous` sentinel under another name, and the difference
# is the whole point.** `anonymous` was reached by FALLBACK — a deployment that
# expected an identity, did not get one, and silently continued under a shared
# owner. Every tenant of such a server wrote into the same prefix and could read
# each other's outputs, and it looked exactly like a working request. There is
# no fallback to this value: it is used only where the deployment has said, in
# its own configuration, that it has no users. A deployment that expects
# identity and lacks one now fails with 401.
#
# A token may never bind it (`verify_jwt` below), or an authenticated caller
# could land in the single-tenant namespace on a server that does have users.
#
# It is the runtime's constant rather than a literal of our own because the
# runtime recognises it: every deployment configured this way sends the same
# string, so telemetry declines it as a person and attributes the run to the
# stream's configured fallback instead. A second spelling here would drift from
# that one, and every single-tenant deployment would then merge onto one
# PostHog person with nothing failing to say so.


# `auto_error=False` so a missing/empty/non-Bearer `Authorization` header
# does NOT raise FastAPI's default `HTTPException` (which would emit
# `application/json` `{"detail": "Not authenticated"}` — the old, pre-RFC-7807
# shape) before our verifiers run. With `auto_error=False`, `HTTPBearer`
# returns `None` in that case, and the verifiers below raise
# `raise_unauthenticated(...)` so the response is the same RFC 7807
# `application/problem+json` document as every other 401 on the surface.
security = HTTPBearer(auto_error=False)


class AuthMode(StrEnum):
    NONE = "none"
    JWT = "jwt"
    API_KEY = "api_key"


class AuthRefusalReason(StrEnum):
    """Why the server refused a caller's own credentials, as the `auth_refusal_reason` field of the line that says so.

    These are the caller's mistakes, answered with a 401 the exception handler records at WARNING with its `error.type`
    and `detail`, so the line naming the reason is diagnosis and logs at DEBUG. A token that verifies but whose
    `user_id` claim is unusable is no caller's mistake: whoever minted it holds the server's secret, so it is the
    deployment's issuer that is misconfigured, and that line stays a WARNING the operator can act on.
    """

    MISSING_BEARER_TOKEN = "missing_bearer_token"
    EXPIRED_TOKEN = "expired_token"
    INVALID_TOKEN = "invalid_token"
    API_KEY_MISMATCH = "api_key_mismatch"


#: The message of every line saying the server refused a caller's own credentials, its reason a field.
CREDENTIALS_REFUSED_MESSAGE = "A caller's credentials were refused"

#: The advice of every line about a verified token whose user id claim the server cannot use.
TOKEN_ISSUER_USER_ACTION = "Have the token issuer put a path-safe user_id claim in every token, never the single-tenant id"


class ForwardedIdentityHeader(StrEnum):
    """HTTP headers a trusted reverse proxy may forward to authenticate
    a caller when `TRUST_FORWARDED_IDENTITY_HEADERS=true`.

    The runner is a generic execution engine: the ONLY piece of identity
    it consumes is an opaque user id, which it scopes S3 storage keys
    under (`<user_id>/...`). Anything else a proxy might want to forward
    (email, OAuth subject, auth method) is metadata the runner has no
    use for — handlers that need it look it up by `user_id` against the
    deployment's own user store.
    """

    USER_ID = "X-User-Id"


class RequestUser(BaseModel):
    """Authenticated caller identity available to route handlers.

    Holds only `user_id` by design — the runner is a generic execution engine
    and does not own user metadata (email, name, OAuth subject). Deployments
    that need that data look it up by `user_id` against their own user store.
    """

    user_id: str = Field(..., description="Opaque caller identifier supplied by the auth layer or the trusted proxy")


def _set_request_user(request: Request, user_id: str) -> None:
    """Store caller identity on request.state for downstream handlers."""
    request.state.user = RequestUser(user_id=user_id)


def get_auth_mode() -> AuthMode:
    """Read AUTH_MODE from environment. Defaults to 'none'."""
    raw = get_optional_env("AUTH_MODE")
    if not raw:
        return AuthMode.NONE
    try:
        return AuthMode(raw)
    except ValueError:
        log.warning(
            "An unknown authentication mode was replaced by no authentication",
            fields={"env_var": "AUTH_MODE", "auth_mode": raw, USER_ACTION_FIELD: "Set AUTH_MODE to none, jwt or api_key"},
        )
        return AuthMode.NONE


async def verify_jwt(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict[str, Any]:
    """Validate JWT token from Authorization header using JWT_SECRET_KEY."""
    if credentials is None:
        # Missing, empty, or non-Bearer `Authorization` header. `HTTPBearer`
        # is configured with `auto_error=False` so this branch (rather than
        # FastAPI's default `HTTPException`) shapes the response — same RFC
        # 7807 `application/problem+json` as every other 401.
        log.debug(CREDENTIALS_REFUSED_MESSAGE, fields={"auth_mode": AuthMode.JWT, "auth_refusal_reason": AuthRefusalReason.MISSING_BEARER_TOKEN})
        raise_unauthenticated("Missing or malformed Authorization header")

    jwt_secret = get_optional_env("JWT_SECRET_KEY")
    if not jwt_secret:
        log.error(
            "An environment variable the authentication mode requires is not set", fields={"env_var": "JWT_SECRET_KEY", "auth_mode": AuthMode.JWT}
        )
        raise_internal_server_error("Server configuration error: JWT_SECRET_KEY not configured", error_type=ErrorType.SERVER_MISCONFIGURED)

    token = credentials.credentials

    try:
        payload = jwt.decode(  # type: ignore[reportUnknownMemberType]
            token,
            jwt_secret,
            algorithms=[JWT_ALGORITHM],
        )

        # The caller identifier MUST be supplied as an explicit `user_id`
        # claim. We deliberately do NOT fall back to the standard `sub`
        # claim. The id is opaque (any scheme is fine — see `is_safe_user_id`);
        # we only reject values that aren't a single path-safe segment, since
        # the id becomes the owner segment of every storage key.
        user_id = payload.get("user_id")
        if not user_id:
            log.warning("A verified token has no user id claim", fields={USER_ACTION_FIELD: TOKEN_ISSUER_USER_ACTION})
            raise_unauthenticated("Invalid token: missing user_id claim", error_type=ErrorType.INVALID_TOKEN)
        if not isinstance(user_id, str) or not is_safe_user_id(user_id):
            # The claim is refused, so it is not `user.id`, which names an authenticated caller and is always a string:
            # the line carries the type the claim was decoded as, and never its value.
            log.warning(
                "A verified token's user id claim is not a path-safe segment",
                fields={"claim_type": type(user_id).__name__, USER_ACTION_FIELD: TOKEN_ISSUER_USER_ACTION},
            )
            raise_unauthenticated("Invalid token: user_id claim must be a single path-safe segment", error_type=ErrorType.INVALID_TOKEN)
        if user_id == SINGLE_TENANT_USER_ID:
            # Path-safe, but reserved for the no-user-model deployment. An
            # authenticated token must not claim it, or that caller's runs would
            # land in the single-tenant namespace of a server that DOES have
            # users — beside whatever a no-auth deployment of the same image
            # wrote there.
            log.warning("A verified token's user id claim is the reserved single-tenant id", fields={USER_ACTION_FIELD: TOKEN_ISSUER_USER_ACTION})
            raise_unauthenticated(
                f"Invalid token: user_id claim must not be the reserved {SINGLE_TENANT_USER_ID!r} value",
                error_type=ErrorType.INVALID_TOKEN,
            )
        _set_request_user(request, user_id=user_id)

        return payload

    except jwt.ExpiredSignatureError:
        log.debug(CREDENTIALS_REFUSED_MESSAGE, fields={"auth_mode": AuthMode.JWT, "auth_refusal_reason": AuthRefusalReason.EXPIRED_TOKEN})
        raise_unauthenticated("Token expired", error_type=ErrorType.TOKEN_EXPIRED)
    except jwt.InvalidTokenError as exc:
        log.debug(
            CREDENTIALS_REFUSED_MESSAGE,
            fields={"auth_mode": AuthMode.JWT, "auth_refusal_reason": AuthRefusalReason.INVALID_TOKEN, **error_fields(exc=exc)},
        )
        raise_unauthenticated("Invalid token", error_type=ErrorType.INVALID_TOKEN)


async def verify_api_key(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]) -> str:
    """Validate static API key from Authorization header against API_KEY env var.

    No user identity is available with static API keys — this is a shared developer key.
    """
    if credentials is None:
        # Missing, empty, or non-Bearer `Authorization` header. See the
        # matching branch in `verify_jwt` for why this lives here and not
        # in `HTTPBearer`'s default `auto_error=True` behavior.
        log.debug(CREDENTIALS_REFUSED_MESSAGE, fields={"auth_mode": AuthMode.API_KEY, "auth_refusal_reason": AuthRefusalReason.MISSING_BEARER_TOKEN})
        raise_unauthenticated("Missing or malformed Authorization header")

    api_key = get_optional_env("API_KEY")

    if not api_key:
        log.error("An environment variable the authentication mode requires is not set", fields={"env_var": "API_KEY", "auth_mode": AuthMode.API_KEY})
        raise_internal_server_error("Server configuration error: API_KEY not configured", error_type=ErrorType.SERVER_MISCONFIGURED)

    if credentials.credentials != api_key:
        log.debug(CREDENTIALS_REFUSED_MESSAGE, fields={"auth_mode": AuthMode.API_KEY, "auth_refusal_reason": AuthRefusalReason.API_KEY_MISMATCH})
        raise_unauthenticated("Invalid authentication token", error_type=ErrorType.INVALID_TOKEN)

    return credentials.credentials


async def no_auth(request: Request) -> None:
    """No-op auth dependency for AUTH_MODE=none.

    With no trusted proxy configured this binds no identity, and the deployment
    is treated as single-tenant (see `SINGLE_TENANT_USER_ID`). If the API sits behind a trusted
    reverse proxy / API gateway that authenticates callers and forwards the
    caller identifier via the `X-User-Id` header, set
    TRUST_FORWARDED_IDENTITY_HEADERS=true to read it. That single header is
    the only thing the runner trusts from a forwarded request — any other
    `X-User-*` headers a caller might attach are ignored.

    The header is NOT trusted unless that env var is set, because any
    external client could otherwise forge it when the API is reachable
    directly. With the flag enabled, you are responsible for ensuring your
    proxy strips `X-User-Id` from inbound requests before adding its own.
    """
    if get_optional_env("TRUST_FORWARDED_IDENTITY_HEADERS") != "true":
        return

    user_id = request.headers.get(ForwardedIdentityHeader.USER_ID)
    if not user_id:
        # **This used to stay anonymous, and that was the bug.** Turning this flag
        # on is a deployment stating "a proxy in front of me authenticates every
        # caller". A request arriving without the header therefore means the proxy
        # is missing, misconfigured, or bypassed — and continuing under a shared
        # owner is how a multi-tenant server silently becomes a single namespace
        # where every tenant reads the others' outputs. It is now a hard failure.
        log.warning(
            "No user id was forwarded though forwarded identity headers are trusted",
            fields={
                "env_var": "TRUST_FORWARDED_IDENTITY_HEADERS",
                USER_ACTION_FIELD: "Make sure the proxy in front of the server authenticates every request and forwards X-User-Id",
            },
        )
        raise_unauthenticated("Identity required: no X-User-Id was forwarded", error_type=ErrorType.INVALID_TOKEN)
    if not is_safe_user_id(user_id):
        # A non-empty but path-unsafe id: the proxy intended to authenticate
        # someone and sent a malformed value. Fail closed.
        # No value: the header is refused, so it names no caller, and it is whatever text anyone reaching the server sent.
        log.warning("A forwarded user id is not a path-safe segment and the request was refused")
        raise_bad_request("Forwarded X-User-Id must be a single path-safe segment", error_type=ErrorType.BAD_REQUEST)

    _set_request_user(request, user_id=user_id)


async def get_request_user(request: Request) -> RequestUser | None:
    """Dependency to retrieve the authenticated user identity.

    Returns the RequestUser if identity was established during auth, or None
    if no identity is available (e.g. static API key, or no auth).

    Usage in route handlers:
        async def my_endpoint(user: Annotated[RequestUser | None, Depends(get_request_user)]):
            if user:
                log.debug("Serving a request", fields={OTelLogAttr.USER_ID: user.user_id})
    """
    return getattr(request.state, "user", None)


def get_auth_dependency() -> Any:
    """Select authentication dependency based on AUTH_MODE env var.

    - none: No authentication (self-hosted default, or behind API Gateway)
    - jwt: Validate JWT tokens
    - api_key: Validate static API key
    """
    auth_mode = get_auth_mode()
    match auth_mode:
        case AuthMode.NONE:
            return no_auth
        case AuthMode.JWT:
            return verify_jwt
        case AuthMode.API_KEY:
            return verify_api_key
