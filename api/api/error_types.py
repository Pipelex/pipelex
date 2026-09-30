"""Centralized `error_type` symbols for API-authored error responses.

Every fixed (non-dynamic) `error_type` an API-authored error emits lives here
so call sites reference symbols, not literals — easier to grep, rename, and
document. The `api.errors` helpers stamp one of these onto the RFC 7807
problem document as the `error_type` extension member.

Pipelex domain errors carry their own open-ended `error_type` (the exception
class name, from the `ErrorReport`) and are NOT enumerated here — they are
deliberately not a fixed set.
"""

from enum import StrEnum


class ErrorType(StrEnum):
    # Authentication / authorization
    UNAUTHENTICATED = "Unauthenticated"
    FORBIDDEN = "Forbidden"
    # A caller asked to run in an orchestration_mode this deployment forbids overriding
    # (per-request override is off — see `allow_request_orchestration_mode_override` in api.toml).
    # A 403: the deployment policy refuses to honor the requested mode.
    ORCHESTRATION_MODE_OVERRIDE_FORBIDDEN = "OrchestrationModeOverrideForbidden"
    INVALID_TOKEN = "InvalidToken"
    TOKEN_EXPIRED = "TokenExpired"
    SERVER_MISCONFIGURED = "ServerMisconfigured"

    # A caller hit `/start` on a deployment whose resolved orchestration mode cannot do genuine
    # async (its orchestrator's `supports_fire_and_forget` is False — e.g. the in-process `direct`
    # base). `/start` is fire-and-forget by nature, so rather than silently running blocking and
    # acking, it refuses HONESTLY with a 400: use `/execute` (synchronous) instead. Checked AFTER
    # the override policy, so a forbidden per-request override still 403s first.
    START_REQUIRES_ASYNC_ORCHESTRATION = "StartRequiresAsyncOrchestration"

    # Request validation
    BAD_REQUEST = "BadRequest"
    VALIDATION_ERROR = "ValidationError"
    INVALID_JSON = "InvalidJSON"
    # A run request's body carries, at any depth, an object key a kajson decoder reads as a class
    # marker: `__class__`, `__module__`, or anything starting with `__kajson`. A 422, not data: the
    # run body is plain JSON, and such a key would make a later kajson round trip of the inputs
    # import and instantiate whatever class the caller named.
    RESERVED_OBJECT_KEY = "ReservedObjectKey"
    INVALID_CALLBACK_URLS = "InvalidCallbackUrls"
    # A run request's `storage_scope` extra is not one to three path-safe segments. A 422, not a
    # 500 from deep in the run: the value becomes a storage key prefix, so a `..` escapes the tenant.
    INVALID_STORAGE_SCOPE = "InvalidStorageScope"
    # A run request's `read_scope` extra is not one to three path-safe segments, or the run's storage
    # scope does not lie under it, so the run could not read back what it writes.
    INVALID_READ_SCOPE = "InvalidReadScope"
    # A run request's `analytics_groups` extra is not a mapping of group type to group key within
    # the runtime's charset and entry cap (`pipelex.system.run_extras`).
    INVALID_ANALYTICS_GROUPS = "InvalidAnalyticsGroups"
    INVALID_MODEL_CATEGORY = "InvalidModelCategory"
    INVALID_BASE64 = "InvalidBase64"
    PAYLOAD_TOO_LARGE = "PayloadTooLarge"
    # A run request carried a malformed method bundle (`bundle_b64` / `files`): a corrupt zip, an
    # unsafe entry name (absolute path or `..` traversal), or both transport forms supplied at once.
    INVALID_BUNDLE = "InvalidBundle"
    # A method carrying custom Python (`.py` in a bundle, or in a fetched `method_ref` package)
    # reached a deployment that is NOT sandbox-hosted. Running customer code in-process is
    # refused (403): custom code is a sandbox-hosted capability only. Use a sandbox-hosted
    # deployment. (On a sandbox-hosted deployment, a bundle or a fetched package declaring Python
    # STRUCTURE classes is still refused — that is pipelex's `MethodStructuresRefusedError`, not this.)
    CUSTOM_CODE_REQUIRES_SANDBOX = "CustomCodeRequiresSandbox"

    # A caller selected a closure by a REGISTRY-FORM `method_ref` (not a `github.com/...`
    # address) on a tooling route. Address-form refs resolve server-side (fetch at tag, package
    # located by manifest identity); the registry form is the packaging program's closing phase,
    # so it keeps an honest 501 until a method registry exists — never a silent empty verdict.
    METHOD_REF_NOT_SUPPORTED = "MethodRefNotSupported"

    # Misc
    PACKAGE_NOT_FOUND = "PackageNotFound"
    # The `error_type` for the catch-all 500 emitted by `handle_unexpected_error`
    # (any failure matched by no more-specific handler — not an `ApiError`, a
    # `RequestValidationError`, a `PipelexError`, or an orchestrator plugin's mapped
    # transport exception). Stays in this enum so the same `build_problem_document_from_api_error`
    # builder renders it — same shape as every other API-authored 500.
    INTERNAL_SERVER_ERROR = "InternalServerError"
