from pipelex.base_exceptions import ErrorDomain, PipelexError


class BundleResourceError(PipelexError):
    """Raised when a bundle resource cannot be read: stored bytes that no longer match their digest, or a read the resource cannot serve."""


class BundleResourcePathError(PipelexError):
    """Raised when a file submitted with a bundle is keyed by a path that cannot name a file inside the bundle.

    A resource's key is the path a step names, relative to the bundle and written with forward slashes: an absolute
    path, a `..` segment, a backslash, a drive colon and an empty path are refused, and so are two keys naming the
    same file. The path is the caller's own, so the message is theirs to read, and the same request is refused again.
    """

    error_domain = ErrorDomain.INPUT
    retryable = False
    _authors_caller_facing_message = True


class BundleResourceNotNamedError(PipelexError):
    """Raised when a file submitted with a bundle is named by none of its steps.

    Every file a caller submits must be one a step reads, such as a `PipeDocGen` step's `template_file`, so a
    misspelt key fails loudly rather than leaving the step without its file. The message names the caller's paths, and
    the same request is refused again.
    """

    error_domain = ErrorDomain.INPUT
    retryable = False
    _authors_caller_facing_message = True


class BundleResourcesTooLargeError(PipelexError):
    """Raised when the files a bundle's steps read when the method loads, such as HTML templates, are too large in total.

    They travel inline with the method wherever it runs, so their total is bounded (`MAX_LOAD_STAGE_RESOURCES_BYTES`),
    whereas a file read only when its step runs, such as an office template, travels by reference to the run's storage.
    The message names the caller's paths and the limit, and the same request is refused again.
    """

    error_domain = ErrorDomain.INPUT
    retryable = False
    _authors_caller_facing_message = True
