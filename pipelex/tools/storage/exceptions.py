from typing import Any, ClassVar

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexConfigError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.exceptions import ToolError


class StorageError(ToolError):
    """Base exception for storage-related errors."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class StorageConfigError(PipelexConfigError, StorageError):
    """Raised when a storage configuration is invalid.

    It shares the configuration code rather than a storage one: an operator handles it like any other
    configuration error.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = PipelexErrorCode.CONFIG_INVALID


class StorageFileNotFoundError(StorageError):
    """Raised when a requested file does not exist in storage.

    A stored file a run wrote or was handed has vanished, which is nobody's input, so the default is
    ``pipelex.storage.not_found``. A URI of the wrong scheme reaching a provider is a routing fault of the
    runtime, ``runtime.unexpected``.
    """

    error_code = ErrorCodeSet(default=PipelexErrorCode.STORAGE_NOT_FOUND, others=(CoreCode.RUNTIME_UNEXPECTED,))


class StorageNotConfiguredError(StorageError):
    """Raised when a ``pipelex-storage://`` URI must be read on a runtime that has no storage provider."""

    error_code = PipelexErrorCode.STORAGE_NOT_CONFIGURED


class StorageInvalidUriError(StorageError):
    """Raised when a URI is invalid (e.g., path traversal attempt or absolute path).

    The provider cannot tell who supplied the key, so the default is ``security.input_path_refused``, the
    reading of the input seam where a caller passes a storage key. A site that knows a pipe or a function
    produced the key chooses ``security.method_url_refused``, and a payload codec that finds a reference it did
    not write chooses ``runtime.unexpected``.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.SECURITY_INPUT_PATH_REFUSED,
        others=(CoreCode.SECURITY_METHOD_URL_REFUSED, CoreCode.RUNTIME_UNEXPECTED),
    )


class StorageInvalidKeyError(StorageError):
    """Raised when a storage key is invalid (e.g., contains scheme prefix)."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class StorageLocalError(StorageError):
    """Raised when a local filesystem storage operation fails.

    A permission or disk-full error does not heal on retry: whoever runs the runtime fixes the directory.
    """

    error_code = CoreCode.RUNTIME_MISCONFIGURED


class StorageS3Error(StorageError):
    """Raised when an S3 storage operation fails.

    An S3 failure is ``pipelex.storage.unavailable`` unless S3 names its cause: a missing bucket is the
    configured bucket name, ``pipelex.config.invalid``; credentials S3 refuses are
    ``pipelex.config.credential_refused``; and credentials the runtime could not find are
    ``pipelex.config.credential_missing``.
    """

    error_code = ErrorCodeSet(
        default=PipelexErrorCode.STORAGE_UNAVAILABLE,
        others=(
            PipelexErrorCode.CONFIG_INVALID,
            PipelexErrorCode.CONFIG_CREDENTIAL_REFUSED,
            PipelexErrorCode.CONFIG_CREDENTIAL_MISSING,
        ),
    )

    @override
    def problem_params(self) -> dict[str, Any]:
        # The kind of storage `pipelex.storage.unavailable` names; a configuration code declares no such parameter.
        return {"scheme": "s3"}


class StorageGcpError(StorageError):
    """Raised when a GCP storage operation fails.

    A GCS failure is ``pipelex.storage.unavailable`` unless GCS refuses the credentials, which is
    ``pipelex.config.credential_refused``.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=PipelexErrorCode.STORAGE_UNAVAILABLE, others=(PipelexErrorCode.CONFIG_CREDENTIAL_REFUSED,)
    )

    @override
    def problem_params(self) -> dict[str, Any]:
        # The kind of storage `pipelex.storage.unavailable` names; a configuration code declares no such parameter.
        return {"scheme": "gcs"}


class StorageGcpCredentialsError(StorageGcpError):
    """Raised when GCP credentials file is not found or invalid."""

    error_code = PipelexErrorCode.CONFIG_FILE_MISSING
