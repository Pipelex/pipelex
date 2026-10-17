"""The runner's own error classes, each carrying its registry code.

Every class here is a :class:`~pipelex.base_exceptions.PipelexError` that declares its ``error_code`` in its own
body, as pipelex's error model requires (``pipelex/errors/error_code_declaration.py``), and the runner's gate test,
``tests/unit/test_error_code_gate.py``, fails the build on one that does not. They live in this module, rather than
beside the code that raises them, as every error class does: the same gate refuses one defined outside an
``exceptions.py`` or ``<topic>_exceptions.py`` module.

The refusals the runner authors at its own boundary, a request it cannot parse or accept, a credential it refuses, a
method tree it cannot read, a deployment policy, are raised as these classes like any other pipelex error, so the one
global handler (``pipelex_api.exception_handlers.handle_pipelex_error``) answers each with its problem document, in the
view of the request's reader, and logs the security event of one that is a security refusal. A raise site chooses the
code its class declares with ``with_error_code`` and gives the code's parameters with ``with_params``; the problem's
``detail`` and ``next_step`` are the code's sentences, while the message stays the operator's, in ``diagnostics``.
"""

from enum import StrEnum, unique
from typing import Any

from mthds.protocol.problem.models import ProblemLocation
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeSet
from pipelex.errors.problem import make_location
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.errors.security_target import SecurityTargetClass
from typing_extensions import override


class RequestFieldConflictError(PipelexError, ValueError):
    """A request whose fields contradict each other, refused by its model's validator, naming the field to change.

    Also a ``ValueError``, since a model validator raises it, which pydantic reports as a fault of the body as a whole,
    located at no field. The request's refusal reads it from the fault's context (``pipelex_api.request_refusals``) and
    names its ``field`` instead, so the `request.invalid` item tells the caller which field to change or drop.
    """

    error_code = CoreCode.REQUEST_INVALID

    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message)
        self.field = field

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"field": self.field}


class ApiBootConfigError(PipelexError):
    """Raised at startup when the deployment's orchestration config cannot boot coherently."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class InvalidAuthModeError(PipelexError):
    """Raised at startup when `AUTH_MODE` holds a value that is not an `AuthMode` member."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class CallbackUrlRefusedError(PipelexError, ValueError):
    """A completion callback URL the SSRF rules refuse: a scheme other than http or https, or a disallowed host.

    Also a ``ValueError``, since the check runs inside the request model's validator, which turns only a ``ValueError``
    into a validation error. The run routes find it there and raise it again, so it answers with its own code and logs
    its security event, with the class of destination it states and never the URL.
    """

    error_code = CoreCode.SECURITY_INPUT_URL_REFUSED

    @override
    def problem_params(self) -> dict[str, Any]:
        target_class = self.security_target_class
        reason: str
        match target_class:
            case SecurityTargetClass.SCHEME:
                reason = "scheme_not_allowed"
            case (
                SecurityTargetClass.LOOPBACK
                | SecurityTargetClass.PRIVATE
                | SecurityTargetClass.LINK_LOCAL
                | SecurityTargetClass.METADATA
                | SecurityTargetClass.FOREIGN_STORAGE_KEY
                | None
            ):
                reason = "host_not_allowed"
        return {"input": "callback_urls", "target_class": target_class, "reason": reason}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(field="callback_urls")


class RunnerRequestError(PipelexError):
    """A request the runner refuses at its own boundary, before it reads a method or runs anything.

    Its code defaults to ``request.invalid``, a field the route's rules refuse, which ``field`` names, as the problem's
    ``field`` parameter and its location. The raise site chooses ``request.malformed`` for a body, or an encoded part of
    one, that cannot be parsed, ``request.too_large`` for a request past one of this runner's size limits,
    ``request.unsupported`` for a form this runner does not accept, ``request.blobs_missing`` for files sent by hash
    that this runner does not hold, and ``request.not_found`` and ``request.method_not_allowed`` for a request no route
    serves.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.REQUEST_INVALID,
        others=(
            CoreCode.REQUEST_MALFORMED,
            CoreCode.REQUEST_TOO_LARGE,
            CoreCode.REQUEST_UNSUPPORTED,
            CoreCode.REQUEST_BLOBS_MISSING,
            CoreCode.REQUEST_NOT_FOUND,
            CoreCode.REQUEST_METHOD_NOT_ALLOWED,
        ),
    )

    def __init__(self, message: str, *, field: str | None = None) -> None:
        """Build the refusal of a request.

        Args:
            message: What is wrong with the request, for the operator's diagnostics.
            field: The refused field, as the request spells it, or a dotted path into the body; `None` when the refusal is
                of the request as a whole.
        """
        super().__init__(message)
        self.field = field

    @override
    def problem_params(self) -> dict[str, Any]:
        if self.field is None:
            return {}
        return {"field": self.field}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(field=self.field)


class RunnerAuthError(PipelexError):
    """A request the runner's authentication refuses.

    Its code defaults to ``auth.invalid_credential``, a credential the runner refuses. The raise site chooses
    ``auth.missing_credential`` when the request carries none, ``auth.credential_expired`` when its token expired, and
    ``pipelex.deployment.token_claims_invalid`` when a token whose signature holds carries claims this runner cannot use,
    which its issuer, not its bearer, must fix, and ``auth.forbidden`` when the request lacks what an operation needs,
    whose ``requirement`` it names, such as the signed target a blob upload needs.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.AUTH_INVALID_CREDENTIAL,
        others=(
            CoreCode.AUTH_MISSING_CREDENTIAL,
            CoreCode.AUTH_CREDENTIAL_EXPIRED,
            CoreCode.AUTH_FORBIDDEN,
            PipelexErrorCode.DEPLOYMENT_TOKEN_CLAIMS_INVALID,
        ),
    )

    def __init__(self, message: str, *, challenge: str | None = None) -> None:
        """Build the refusal of a request's authentication.

        Args:
            message: What the authentication refused, for the operator's diagnostics.
            challenge: The `WWW-Authenticate` challenge the response carries, naming the scheme of the credential the
                deployment reads, `Bearer` for a token or an API key; `None` where it reads no credential of the
                request, as behind a trusted proxy, which a challenge would ask for one the deployment never reads.
        """
        super().__init__(message)
        self.challenge = challenge


class RunnerMisconfiguredError(PipelexError):
    """The runner's own configuration or installation cannot serve the request: a setting is missing or wrong.

    ``component`` names what is misconfigured, such as the environment variable, and only the operator's view reads it.
    """

    error_code = CoreCode.RUNTIME_MISCONFIGURED

    def __init__(self, message: str, *, component: str) -> None:
        super().__init__(message)
        self.component = component

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"component": self.component}


class BlobStoreDamagedError(PipelexError):
    """Bytes the blob store holds under a hash do not hash to it, or are not the size it holds them at.

    The storage failed the read, whether a backend cut it short or an object was damaged, which no caller can repair
    and no upload of theirs changes: ``pipelex.storage.unavailable``, a 503 a caller retries, while a damage that
    persists is the operator's to clear. ``scheme`` is the kind of storage the deployment runs, ``None`` for a storage
    plugin whose kind the registry does not list.
    """

    error_code = PipelexErrorCode.STORAGE_UNAVAILABLE

    def __init__(self, message: str, *, scheme: str | None) -> None:
        super().__init__(message)
        self.scheme = scheme

    @override
    def problem_params(self) -> dict[str, Any]:
        if self.scheme is None:
            return {}
        return {"scheme": self.scheme}


class OrchestrationOverrideForbiddenError(PipelexError):
    """A request choosing an orchestration mode on a deployment that fixes its own."""

    error_code = PipelexErrorCode.DEPLOYMENT_ORCHESTRATION_OVERRIDE_FORBIDDEN

    def __init__(self, message: str, *, requested_mode: str) -> None:
        super().__init__(message)
        self.requested_mode = requested_mode

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"requested_mode": self.requested_mode}


class CustomCodeOrigin(StrEnum):
    """Where a method that ships Python carries it: in the bundle a request sent, or in a package fetched by address."""

    BUNDLE = "bundle"
    PACKAGE = "package"


class CustomCodeRequiresSandboxError(PipelexError):
    """A method shipping Python on a deployment that runs none outside the Daytona sandbox."""

    error_code = PipelexErrorCode.DEPLOYMENT_CUSTOM_CODE_REQUIRES_SANDBOX

    def __init__(self, message: str, *, origin: CustomCodeOrigin) -> None:
        super().__init__(message)
        self.origin = origin

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"origin": self.origin}


class ReservedObjectKeyError(PipelexError):
    """A request body holding an object key a kajson decoder reads as a class marker, which a security rule refuses."""

    error_code = PipelexErrorCode.SECURITY_RESERVED_KEY

    def __init__(self, message: str, *, keys: list[str]) -> None:
        super().__init__(message)
        self.keys = keys

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"keys": self.keys}


@unique
class MethodPackageReason(StrEnum):
    """The `reason` of a `method.package_invalid` this runner raises itself, one member per rule and one per limit.

    Beside them, a refusal of the standard's tree rule gives the standard's own refusal code (`TreeRefusalCode`) as its
    reason. A limit's refusal also gives its `limit`, and each limit has its own reason, so a caller reads which one the
    method passed: a tree's, a request's, a `bundle_b64` archive's or a fetched package's `.mthds` file's.
    """

    # The limits of one method tree.
    TOO_MANY_FILES = "too_many_files"
    FILE_TOO_LARGE = "file_too_large"
    TREE_TOO_LARGE = "tree_too_large"
    # The limits of a request's trees together.
    TOO_MANY_DEPENDENCIES = "too_many_dependencies"
    METHOD_TOO_LARGE = "method_too_large"
    # The limits of a `bundle_b64` archive, on its members and on its decompressed size.
    BUNDLE_TOO_MANY_FILES = "bundle_too_many_files"
    BUNDLE_TOO_LARGE = "bundle_too_large"
    # The limit on one `.mthds` file of a package fetched by `method_ref` for a tooling route.
    MTHDS_FILE_TOO_LARGE = "mthds_file_too_large"
    # The method's own tree holds no `.mthds` bundle.
    NO_BUNDLE = "no_bundle"
    # The manifest of a shipped package or of a dependency tree.
    MANIFEST_MISSING = "manifest_missing"
    MANIFEST_INVALID = "manifest_invalid"
    PACKAGE_NAME_INVALID = "package_name_invalid"
    # Two dependencies a reference could not tell apart.
    DEPENDENCY_ADDRESS_COLLISION = "dependency_address_collision"
    # A fetched package holds a file whose name is not UTF-8 text.
    FILE_NAME_NOT_UTF8 = "file_name_not_utf8"


class RequestMethodError(PipelexError):
    """A method the request carries, or names by address, that the runner refuses to read as a method.

    Its code defaults to ``method.package_invalid``, a tree breaking a rule of the method's package, whose ``reason``
    and ``path`` or ``limit`` the raise site gives. The raise site chooses ``method.syntax`` for a bundle that is not
    text, ``method.resource_missing`` for a file reference naming no file of the tree, and
    ``security.input_path_refused`` for a path of the tree that would leave its root, a security refusal. ``file`` names
    the file of the tree the refusal is about, when there is one.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.METHOD_PACKAGE_INVALID,
        others=(CoreCode.METHOD_SYNTAX, CoreCode.METHOD_RESOURCE_MISSING, CoreCode.SECURITY_INPUT_PATH_REFUSED),
    )

    def __init__(self, message: str, *, file: str | None = None) -> None:
        super().__init__(message)
        self.file = file

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(file=self.file)
