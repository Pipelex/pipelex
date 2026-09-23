"""The API client the Pipelex CLIs run methods through, named `pipelex-cli` in its `User-Agent`.

Every request a client sends to an MTHDS runner or to the hosted API carries a `User-Agent`
built from product tokens, outermost first, so the server can tell which program sent it.
The CLIs' API runner is `mthds`'s `MthdsAPIClient`, which accepts an `app_info` to put in
front of its own `mthds-python/<version>` token, so a CLI request reads:

    pipelex-cli/<pipelex version> mthds-python/<mthds version> python/<version> (<os>; <arch>)

Only the CLI entry path builds its client here. A program using `pipelex` as a library
constructs its own client and names itself, so its requests are never labelled `pipelex-cli`.
"""

from __future__ import annotations

from mthds.runners.api.client import MthdsAPIClient
from mthds.runners.api.user_agent import AppInfo

from pipelex.tools.misc.package_utils import get_package_version

#: The CLIs' registered token name in the client-identification registry.
PIPELEX_CLI_APP_NAME = "pipelex-cli"


def pipelex_cli_app_info() -> AppInfo:
    """The `app_info` naming the Pipelex CLIs, versioned with the installed `pipelex` package."""
    return AppInfo(name=PIPELEX_CLI_APP_NAME, version=get_package_version())


def make_pipelex_cli_api_client() -> MthdsAPIClient:
    """Build the API client a CLI command runs a method through, identified as `pipelex-cli`.

    The API key and base URL resolve as `MthdsAPIClient` resolves them (`MTHDS_API_KEY`,
    `MTHDS_BASE_URL`, or `~/.mthds/config`).

    Raises:
        ClientAuthenticationError: If no API key or base URL can be resolved.
    """
    return MthdsAPIClient(app_info=pipelex_cli_app_info())
