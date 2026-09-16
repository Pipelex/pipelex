from pydantic import HttpUrl, TypeAdapter, ValidationError

from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.package_utils import get_package_version

URL_MAX_LENGTH = 2048

# URI schemes that are handled internally and should not be validated
_SKIP_VALIDATION_PREFIXES = ("data:", "pipelex-storage://")

# The syntax of an http(s) URL, as pydantic reads it: scheme, host, no whitespace, a length bound.
_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


def validate_http_url_syntax(*, url: str) -> None:
    """Check that ``url`` is a well-formed http(s) URL, without touching the network.

    Raises:
        ValueError: If the URL does not parse as an http(s) URL.
    """
    try:
        _HTTP_URL_ADAPTER.validate_python(url)
    except ValidationError as exc:
        first_error = exc.errors()[0]["msg"] if exc.errors() else "not a valid http(s) URL"
        msg = f"URL '{url}' is not a valid http(s) URL: {first_error}"
        raise ValueError(msg) from exc


def get_user_agent() -> str:
    """The User-Agent pipelex sends when it fetches a resource on a user's behalf: ``Pipelex/<version>``.

    Product and version only, the shape a browser or an SDK sends. The crawler convention of a
    URL in parentheses is what bot walls key on: the same host that serves ``Pipelex/0.57.0``
    in under a second stalls ``Pipelex/0.57.0 (https://pipelex.com)`` until the timeout.
    """
    version = get_package_version()
    return f"Pipelex/{version}"


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
