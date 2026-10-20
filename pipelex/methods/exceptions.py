from typing import Any, ClassVar, Self

from mthds.package.lock_file import LOCK_FILENAME
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.methods.package_reason import MethodPackageReason


class MethodRefError(PipelexError):
    """Base class for errors while resolving a method reference (`<address>[@<tag>]`).

    Every subclass describes the caller's own reference or the package it points at.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class MethodRefParseError(MethodRefError):
    """The method reference does not match the `<address>[@<tag>]` grammar, or names an address this runtime does not fetch."""

    error_code = ErrorCodeSet(default=CoreCode.REQUEST_INVALID, others=(CoreCode.REQUEST_UNSUPPORTED,))

    @override
    def problem_params(self) -> dict[str, Any]:
        # The reference is the request's `method_ref`; an address it does not fetch is one off GitHub.
        return {"field": "method_ref", "reason": "address_not_on_github"}


class MethodFetchError(MethodRefError):
    """Fetching the repository behind a method reference failed (clone, tag verification, or commit resolution).

    The default ``method.fetch_failed`` is a clone, a resolution or a timeout that failed; a raise site chooses
    ``pipelex.config.dependency_missing`` when git is not installed on this host, ``method.not_found`` when the
    repository holds no such tag or no commit, and ``method.package_invalid`` for a fetched package that breaks a
    package rule.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.METHOD_FETCH_FAILED,
        others=(PipelexErrorCode.CONFIG_DEPENDENCY_MISSING, CoreCode.METHOD_NOT_FOUND, CoreCode.METHOD_PACKAGE_INVALID),
    )

    method_ref: str | None = None

    def for_method_ref(self, *, method_ref: str) -> Self:
        """Name the method reference whose fetch failed, which the codes' sentences name; returns this error."""
        self.method_ref = method_ref
        return self

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"method_ref": self.method_ref}


class MethodPackageNotFoundError(MethodRefError):
    """No package inside the fetched repository matches the requested address by manifest identity."""

    error_code = CoreCode.METHOD_NOT_FOUND


class MethodPackageAmbiguityError(MethodRefError):
    """More than one package inside the fetched repository matches the requested address."""

    error_code = CoreCode.METHOD_AMBIGUOUS


class MethodPackageTooLargeError(MethodRefError):
    """Fetched content exceeds a ceiling: the selected package's file count or total bytes, or the repository's manifest scan."""

    error_code = CoreCode.METHOD_PACKAGE_INVALID


class MethodPackageSymlinkError(MethodRefError):
    """The fetched package contains a symlink, which fetched packages must not carry (it would bypass the content scans)."""

    error_code = CoreCode.METHOD_PACKAGE_INVALID

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"reason": MethodPackageReason.SYMLINK}


class MethodStructuresRefusedError(MethodRefError):
    """The method declares Python structure classes, which hosted execution refuses to import into its own process.

    Raised for a fetched package before it is installed, and for any sandbox-hosted library load,
    whatever the content's origin: an inline bundle, a stored method or a host directory.
    """

    error_code = PipelexErrorCode.DEPLOYMENT_PYTHON_STRUCTURES_REFUSED


class MethodInstallError(MethodRefError):
    """Installing a fetched method package into the installed-methods directory failed (occupied target, path escape, or copy failure).

    The default ``pipelex.config.invalid`` is an installed-methods directory that cannot take the package; a package
    whose name escapes the directory or that carries no manifest chooses ``method.package_invalid``.
    """

    error_code = ErrorCodeSet(default=PipelexErrorCode.CONFIG_INVALID, others=(CoreCode.METHOD_PACKAGE_INVALID,))


class MethodFetchDisabledError(MethodRefError):
    """An address-referenced method is not installed and fetch-on-miss is disabled, so it cannot be fetched."""

    error_code = CoreCode.METHOD_DEPENDENCY_MISSING


class MethodDependencyFetchError(MethodRefError):
    """An address-referenced method is not installed and fetching it failed (or its address is not fetchable)."""

    error_code = CoreCode.METHOD_DEPENDENCY_MISSING


class MethodDependencyNotShippedError(MethodRefError):
    """An address-referenced method the caller did not ship, under a resolution that reads nothing installed and fetches nothing."""

    error_code = CoreCode.METHOD_DEPENDENCY_MISSING


class MethodLockInvalidError(MethodRefError):
    """The `methods.lock` of a method calling a dependency the runtime fetched cannot be read, so it cannot verify the dependency."""

    error_code = CoreCode.METHOD_PACKAGE_INVALID

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"reason": MethodPackageReason.LOCK_INVALID, "path": LOCK_FILENAME}


class MethodLockMismatchError(MethodRefError):
    """A dependency the runtime fetched holds a tree whose digest is not the one the calling method's `methods.lock` records."""

    error_code = CoreCode.SECURITY_INTEGRITY_MISMATCH
