from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeSet


class BundleResourcePathError(PipelexError):
    """Raised when a file submitted with a bundle is keyed by a path that cannot name a file inside the bundle.

    A submitted file's key is the path a step names, relative to the bundle and written with forward slashes: an
    absolute path, a `..` segment, a backslash, a drive colon and an empty path are refused, and so are two keys naming
    the same file, or a key the tree of the submitted files cannot hold, such as one colliding with another once
    case-folded, or naming a file already submitted, from a library directory or with the request, with other bytes.
    The path is the caller's own, so the message is theirs to read, and the same request is refused again. A path that
    leaves the bundle, absolute, naming a drive or climbing with `..`, is ``security.input_path_refused``; a path of
    the wrong shape, and paths that each could name a file but that cannot make one tree together, choose
    ``request.invalid`` (``pipelex.core.bundle_resources.bundle_resource.path_refusal_code``).
    """

    error_code = ErrorCodeSet(default=CoreCode.SECURITY_INPUT_PATH_REFUSED, others=(CoreCode.REQUEST_INVALID,))
    _authors_caller_facing_message = True


class BundleResourceNotNamedError(PipelexError):
    """Raised when a file submitted with a bundle is named by none of its steps.

    Every file a caller submits must be one a step reads, such as a `PipeDocGen` step's `template_file`, so a
    misspelt key fails loudly rather than leaving the step without its file. The message names the caller's paths, and
    the same request is refused again.
    """

    error_code = CoreCode.REQUEST_INVALID
    _authors_caller_facing_message = True
