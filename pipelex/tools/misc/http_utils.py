from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.urls import URLs

URL_MAX_LENGTH = 2048

# URI schemes that are handled internally and should not be validated
_SKIP_VALIDATION_PREFIXES = ("data:", "pipelex-storage://")


def get_user_agent() -> str:
    version = get_package_version()
    homepage_url = URLs.homepage
    return f"Pipelex/{version} ({homepage_url})"


def validate_url_resource_exists(url: str) -> None:
    """Validate that a URL points to an existing resource, without touching the network.

    By the time a URL reaches DocumentContent/ImageContent, it should already
    be resolved (absolute path or fully qualified URL).

    For local file paths: checks that the file exists on disk.
    For HTTP/HTTPS URLs: no check at all. The downstream extractor is the source
    of truth for remote resources, and this function runs in the pipe router's
    input pre-check, which under an orchestrator such as Temporal is workflow
    code: a blocking request there trips the deadlock detector and the run is
    retried until it times out. A remote probe never changed the outcome anyway
    (it only logged), so there is nothing to move elsewhere.
    Skips validation for internal URIs (base64 data URLs, pipelex-storage://).

    Raises:
        ValueError: If a local file path does not exist.
    """
    if url.startswith(_SKIP_VALIDATION_PREFIXES):
        return

    if url.startswith(("http://", "https://")):
        return

    _validate_local_path(url)


def _validate_local_path(url: str) -> None:
    if not path_exists(url):
        msg = f"File '{url}' does not exist"
        raise ValueError(msg)
