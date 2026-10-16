"""Centralized `error_type` symbols for API-authored error responses.

Every fixed (non-dynamic) `error_type` an API-authored error emits lives here
so call sites reference symbols, not literals — easier to grep, rename, and
document. The `pipelex_api.errors` helpers stamp one of these onto the RFC 7807
problem document as the `error_type` extension member.

Pipelex domain errors answer their problem document, whose identity is its
registry `code`, and are NOT enumerated here.
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
    # `GET /v1/models/check` was given a `reference` it cannot check: blank once trimmed, a sigil or a
    # namespace with nothing after it, or longer than the route's bound. A reference that parses and
    # resolves nowhere is never refused: it is the `not_found` verdict.
    INVALID_MODEL_REFERENCE = "InvalidModelReference"
    INVALID_BASE64 = "InvalidBase64"
    PAYLOAD_TOO_LARGE = "PayloadTooLarge"
    # A run request carried a malformed method bundle (`bundle_b64` / `files`): a corrupt zip, a
    # bundle with no `.mthds` file, or both transport forms supplied at once.
    INVALID_BUNDLE = "InvalidBundle"
    # A request's map of file entries (`files`, a tree of `dependencies`, a `bundle_b64` archive read as
    # one) is not a method tree the MTHDS standard admits: a key given twice, a key that is not a tree
    # path or names a file the membership rule keeps out of every tree, keys that collide, an empty map,
    # or a malformed entry. A 422 whose `tree_refusal` member carries the standard's refusal code and
    # the paths it names.
    INVALID_METHOD_FILES = "InvalidMethodFiles"
    # A request names, by hash, bytes this runner's blob store does not hold at the stated size. A 422
    # whose `missing_blobs` member lists every such hash at once, so a sender learns in one answer what to
    # upload (`POST /v1/blobs/missing`, then `PUT /v1/blobs/{sha256}`).
    MISSING_BLOBS = "MissingBlobs"
    # A method tree, or a blob, passes one of this runner's limits on a tree's file count, its total
    # size or one file's size (`MAX_METHOD_TREE_FILES`, `MAX_METHOD_TREE_TOTAL_KIB`,
    # `MAX_METHOD_TREE_FILE_KIB`). A 422 naming the limit, refused before any blob is read or uploaded.
    METHOD_TREE_TOO_LARGE = "MethodTreeTooLarge"
    # `PUT /v1/blobs/{sha256}` was sent bytes whose SHA-256 is not the one its path names,
    # `POST /v1/blobs/missing` named one hash twice with different sizes, or a request's hash entry states a size other
    # than the one this runner holds that hash's bytes at, which uploading them again would not change. A 422 whose
    # `mismatched_blobs` member, on a request's entries, lists each such hash with the size held.
    BLOB_MISMATCH = "BlobMismatch"
    # The bytes this runner's blob store holds under a hash do not hash to it: the storage is damaged. A 500 no caller
    # can repair; the operator removes the object, and the blob is then uploaded again.
    BLOB_STORE_CORRUPTED = "BlobStoreCorrupted"
    # `PUT /v1/blobs/{sha256}` was called without the signed query `POST /v1/blobs/missing` names in its upload
    # target, with one whose signature does not hold, or past its expiry. A 403: the upload is not stored.
    BLOB_UPLOAD_NOT_AUTHORIZED = "BlobUploadNotAuthorized"
    # A request's `resources` map keys a submitted file by a path that cannot name a file inside the
    # bundle: absolute, with a `..` segment, a backslash or a colon, empty, or a second spelling of a
    # path already submitted. A 422: the key is the path a step names, relative to the bundle.
    INVALID_RESOURCE_PATH = "InvalidResourcePath"
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
