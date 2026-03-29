import httpx

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
    """Validate that a URL points to an existing resource.

    By the time a URL reaches DocumentContent/ImageContent, it should already
    be resolved (absolute path or fully qualified URL).

    For HTTP/HTTPS URLs: performs a streaming GET request to check reachability.
    For local file paths: checks that the file exists on disk.
    Skips validation for internal URIs (base64 data URLs, pipelex-storage://).

    Raises:
        ValueError: If the resource does not exist or is unreachable.
    """
    if url.startswith(_SKIP_VALIDATION_PREFIXES):
        return

    if url.startswith(("http://", "https://")):
        _validate_http_url(url)
    else:
        _validate_local_path(url)


def _validate_http_url(url: str) -> None:
    user_agent = get_user_agent()
    headers = {"User-Agent": user_agent}
    try:
        response = httpx.head(url, timeout=10, follow_redirects=True, headers=headers)
        if response.status_code == 405:
            # Server doesn't support HEAD — fall back to streaming GET (read only status, not body)
            with httpx.stream("GET", url, timeout=10, follow_redirects=True, headers=headers) as stream_response:
                stream_response.raise_for_status()
        else:
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        msg = f"URL '{url}' returned HTTP {exc.response.status_code}"
        raise ValueError(msg) from exc
    except httpx.ConnectError as exc:
        msg = f"URL '{url}' could not be reached (connection failed)"
        raise ValueError(msg) from exc
    except httpx.TimeoutException as exc:
        msg = f"URL '{url}' timed out"
        raise ValueError(msg) from exc
    except httpx.HTTPError as exc:
        msg = f"URL '{url}' could not be fetched"
        raise ValueError(msg) from exc


def _validate_local_path(url: str) -> None:
    if not path_exists(url):
        msg = f"File '{url}' does not exist"
        raise ValueError(msg)
