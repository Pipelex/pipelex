"""The one place pipelex builds a client for the hosted Pipelex API.

The client is pipelex-sdk's `PipelexAPIClient`, which resolves its own key and base URL: the key from
`PIPELEX_API_KEY`, the base URL from the argument, then `PIPELEX_BASE_URL`, then `https://api.pipelex.com`. The
runtime loads `~/.pipelex/.env` and then `./.env` into the environment when `pipelex.system.environment` is first
imported, which this module does, so a key saved there reaches the client with nothing exported.
"""

from urllib.parse import urlsplit, urlunsplit

from mthds.protocol.exceptions import PipelineRequestError
from pipelex_sdk.client import DEFAULT_API_BASE_URL, PipelexAPIClient
from pipelex_sdk.user_agent import AppInfo

from pipelex.hosted.exceptions import HostedBaseUrlError
from pipelex.system.environment import get_optional_env
from pipelex.tools.misc.package_utils import get_package_version

#: The variable holding the Pipelex API key (`plx_sk_…`), read by the SDK.
PIPELEX_API_KEY_ENV_KEY = "PIPELEX_API_KEY"
#: The variable overriding the hosted API's origin, read by the SDK when no `--base-url` is given.
PIPELEX_BASE_URL_ENV_KEY = "PIPELEX_BASE_URL"
#: The origin a hosted run goes to when neither `--base-url` nor `PIPELEX_BASE_URL` names another.
HOSTED_API_DEFAULT_BASE_URL = DEFAULT_API_BASE_URL
#: The name this runtime gives itself in the `User-Agent` of every hosted request.
_APP_NAME = "pipelex"


def redact_url_for_display(*, url: str) -> str:
    """A URL as a message may show it: its scheme, host, port and path, never its credentials, query or fragment.

    Userinfo becomes `***@`, and a query or a fragment becomes `?…` or `#…`, so the reader still sees what made the URL
    unfit without the secrets it may carry, a password or a token in a query. A value that does not parse as a URL
    is not shown at all.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "<a value that does not parse as a URL>"
    host = parts.hostname or ""
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc = f"{netloc}:{port}"
    if parts.username is not None or parts.password is not None:
        netloc = f"***@{netloc}"
    shown = urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    if parts.query:
        shown += "?…"
    if parts.fragment:
        shown += "#…"
    return shown


def make_hosted_client(*, base_url: str | None = None) -> PipelexAPIClient:
    """Build a hosted API client, the key and the base URL left to the SDK's own resolution.

    Args:
        base_url: The origin to call, `scheme://host[:port]`, as `--base-url` gives it. `None` lets the SDK read
            `PIPELEX_BASE_URL`, then fall back to the hosted API.

    Returns:
        A client not yet started: use it as an async context manager.

    Raises:
        HostedBaseUrlError: If the base URL is not host-only, naming the setting it came from.
    """
    try:
        return PipelexAPIClient(base_url=base_url, app_info=AppInfo(name=_APP_NAME, version=get_package_version()))
    except PipelineRequestError:
        # The SDK's constructor raises this for one reason only: a base URL that is not an origin.
        source = "--base-url" if base_url is not None else PIPELEX_BASE_URL_ENV_KEY
        given = base_url if base_url is not None else get_optional_env(PIPELEX_BASE_URL_ENV_KEY) or ""
        msg = (
            f"The hosted API base URL from {source} is not an origin: {redact_url_for_display(url=given)!r}. "
            "Give scheme://host[:port], with http or https and no path, query or credentials, such as https://api.pipelex.com."
        )
        # Not chained: the SDK's message quotes the rejected value whole, credentials included, and a traceback prints it.
        raise HostedBaseUrlError(msg) from None
