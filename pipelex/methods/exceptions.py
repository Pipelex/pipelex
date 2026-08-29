from typing import ClassVar

from pipelex.base_exceptions import PipelexError


class MethodRefError(PipelexError):
    """Base class for errors while resolving a method reference (`<address>[@<tag>]`).

    Every subclass describes the caller's own reference or the package it points at,
    so the messages are caller-facing by design.
    """

    _declared_title = "Method reference error"
    _authors_caller_facing_message: ClassVar[bool] = True


class MethodRefParseError(MethodRefError):
    """The method reference does not match the `<address>[@<tag>]` grammar."""


class MethodFetchError(MethodRefError):
    """Fetching the repository behind a method reference failed (clone, tag verification, or commit resolution)."""


class MethodPackageNotFoundError(MethodRefError):
    """No package inside the fetched repository matches the requested address by manifest identity."""


class MethodPackageAmbiguityError(MethodRefError):
    """More than one package inside the fetched repository matches the requested address."""


class MethodPackageTooLargeError(MethodRefError):
    """Fetched content exceeds a ceiling: the selected package's file count or total bytes, or the repository's manifest scan."""


class MethodStructuresRefusedError(MethodRefError):
    """The fetched package declares in-process Python structure classes, which hosted execution refuses."""


class MethodInstallError(MethodRefError):
    """Installing a fetched method package into the installed-methods directory failed (occupied target, path escape, or copy failure)."""


class MethodFetchDisabledError(MethodRefError):
    """An address-referenced method is not installed and fetch-on-miss is disabled, so it cannot be fetched."""


class MethodDependencyFetchError(MethodRefError):
    """An address-referenced method is not installed and fetching it failed (or its address is not fetchable)."""
