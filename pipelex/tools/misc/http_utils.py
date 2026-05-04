import httpx

from pipelex import log
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.urls import URLs

URL_MAX_LENGTH = 2048

# URI schemes that are handled internally and should not be validated
_SKIP_VALIDATION_PREFIXES = ("data:", "pipelex-storage://")

# HTTP status codes where HEAD rejection is a known server misconfiguration
# (CDNs, signed URLs, auth-gated endpoints) and a GET fallback is justified.
_HEAD_REJECTED_CODES = {403, 405}


def get_user_agent() -> str:
    version = get_package_version()
    homepage_url = URLs.homepage
    return f"Pipelex/{version} ({homepage_url})"


def validate_url_resource_exists(url: str) -> None:
    """Validate that a URL points to an existing resource.

    By the time a URL reaches DocumentContent/ImageContent, it should already
    be resolved (absolute path or fully qualified URL).

    For HTTP/HTTPS URLs: performs a HEAD request (falling back to a streaming GET
    on 405) as a best-effort reachability probe. Failures are logged as warnings
    but do NOT raise — the downstream extractor is the source of truth, and many
    sites bot-block HEAD/unknown User-Agents with 403/401/429 while still serving
    the actual content fine.
    For local file paths: checks that the file exists on disk.
    Skips validation for internal URIs (base64 data URLs, pipelex-storage://).

    Raises:
        ValueError: If a local file path does not exist. HTTP failures only log a warning.
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
        if response.status_code in _HEAD_REJECTED_CODES:
            log.verbose(f"HEAD request to '{url}' returned {response.status_code}, falling back to streaming GET")
            with httpx.stream("GET", url, timeout=10, follow_redirects=True, headers=headers) as stream_response:
                stream_response.raise_for_status()
        else:
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        msg = f"Pre-flight URL check: URL '{url}' returned HTTP {status_code} (continuing — downstream extractor will decide)"
        # 401/403/429 are typical bot-block codes when servers reject HEAD/unknown User-Agents while still serving real content — keep these quiet.
        if status_code in {401, 403, 429}:
            log.debug(msg)
        else:
            log.warning(msg)
    except httpx.ConnectError:
        msg = f"Pre-flight URL check: URL '{url}' could not be reached (connection failed) (continuing — downstream extractor will decide)"
        log.warning(msg)
    except httpx.TimeoutException:
        msg = f"Pre-flight URL check: URL '{url}' timed out (continuing — downstream extractor will decide)"
        log.warning(msg)
    except httpx.HTTPError:
        msg = f"Pre-flight URL check: URL '{url}' could not be fetched (continuing — downstream extractor will decide)"
        log.warning(msg)


def _validate_local_path(url: str) -> None:
    if not path_exists(url):
        msg = f"File '{url}' does not exist"
        raise ValueError(msg)
