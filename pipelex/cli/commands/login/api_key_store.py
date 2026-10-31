"""Where `pipelex login` keeps the Pipelex API key, and where `pipelex init` looks for one already set.

The key is saved as `PIPELEX_API_KEY` in the `.env` of the home configuration directory (`~/.pipelex/.env`, or under
`PIPELEX_HOME`), the file the runtime loads into the environment at import, so a hosted run finds it with nothing
exported. The file keeps its other lines and is readable by its owner only.

The key keeps the API it was checked against: when the file alone, its own `PIPELEX_BASE_URL` or else the hosted API,
would pair it with another, that base URL is written beside it in the same write. A process that does not inherit the
login shell's environment, a fresh shell or an app launched from the desktop, reads the file alone, and the workshop
(`@pipelex/mcp`) shares the file under the same rule.

The runtime then loads the working directory's `.env`, which wins: a `PIPELEX_API_KEY` line there, even an empty one,
is what every command run in that directory sends, whatever the home file holds.
"""

import os
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values

from pipelex.cli.commands.init.credentials import get_global_env_path, is_unquoted_env_value, read_env_file_value, set_env_file_entries
from pipelex.hosted.client_factory import HOSTED_API_DEFAULT_BASE_URL, PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY

#: The working directory's `.env`, which the runtime loads after the home one (see `pipelex.system.environment`).
WORKING_DIRECTORY_ENV_FILE_NAME = ".env"
# The port each scheme a base URL may carry implies, which two equal base URLs may or may not spell out.
_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


class SavedApiKey(NamedTuple):
    """Where a key was saved, and what was saved beside it."""

    env_path: Path
    #: The base URL written beside the key, because the file alone would have paired the key with another API.
    saved_base_url: str | None = None
    #: The base URL the key was checked against, left out because a `.env` file cannot hold it unquoted, although
    #: the file alone pairs the key with another API.
    unsaved_base_url: str | None = None


def comparable_base_url(*, base_url: str) -> str:
    """A base URL as the client reads it, for comparing two: trailing slashes dropped, scheme and host lowercased, a default port left out.

    A value that is not a plain `http` or `https` origin is only stripped of its trailing slashes, so it stays unequal to
    every origin but its own spelling.
    """
    trimmed = base_url.rstrip("/")
    try:
        parts = urlsplit(trimmed)
        port = parts.port
    except ValueError:
        return trimmed
    scheme = parts.scheme.lower()
    host = parts.hostname
    if scheme not in _DEFAULT_PORTS or not host or parts.username is not None or parts.password is not None:
        return trimmed
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))


def base_url_to_save(*, checked_base_url: str, file_values: dict[str, str | None]) -> str | None:
    """The base URL to write beside the key, or `None` when the file alone already pairs the key with the API that checked it.

    The file alone gives the key its own `PIPELEX_BASE_URL`, an empty one included, or else the hosted API: what a
    process that sets no `PIPELEX_BASE_URL` of its own sends the key to.

    Args:
        checked_base_url: The base URL the key was checked against.
        file_values: The home `.env` as the runtime reads it.
    """
    file_base_url = file_values.get(PIPELEX_BASE_URL_ENV_KEY)
    from_file_alone = HOSTED_API_DEFAULT_BASE_URL if file_base_url is None else file_base_url
    if comparable_base_url(base_url=checked_base_url) == comparable_base_url(base_url=from_file_alone):
        return None
    return checked_base_url


def save_pipelex_api_key(*, api_key: str, checked_base_url: str | None) -> SavedApiKey:
    """Save the key as `PIPELEX_API_KEY` in the home `.env`, with the base URL it was checked against when needed.

    The base URL is written beside the key, in the same write, when the file alone would pair the key with another API
    (see `base_url_to_save`), and both are set in this process's environment.

    Args:
        api_key: A Pipelex API key, already checked to be well formed.
        checked_base_url: The base URL the key was checked against, or `None` when no hosted client could be built to
            check it, which leaves the file's base URL as it is.

    Returns:
        The file it was saved to, and the base URL saved beside the key or left out.
    """
    env_path = get_global_env_path()
    saved_base_url: str | None = None
    unsaved_base_url: str | None = None
    if checked_base_url:
        # Read now, after the check, so a base URL another program wrote to the file meanwhile is decided on too.
        file_values = dotenv_values(env_path) if env_path.is_file() else {}
        base_url = base_url_to_save(checked_base_url=checked_base_url, file_values=file_values)
        if base_url is not None:
            if is_unquoted_env_value(value=base_url):
                saved_base_url = base_url
            else:
                unsaved_base_url = base_url
    entries = {PIPELEX_API_KEY_ENV_KEY: api_key}
    if saved_base_url is not None:
        entries[PIPELEX_BASE_URL_ENV_KEY] = saved_base_url
    set_env_file_entries(env_path=env_path, entries=entries)
    # The rest of this command, init's later steps included, sees the key as a new process would.
    for key, value in entries.items():
        os.environ[key] = value
    return SavedApiKey(env_path=env_path, saved_base_url=saved_base_url, unsaved_base_url=unsaved_base_url)


def find_base_url_env_file() -> Path | None:
    """The `.env` file that gives this process its `PIPELEX_BASE_URL`, or `None` when no file Pipelex loads sets it.

    The working directory's `.env` is loaded last and wins, so it is named when it sets the variable, else the home one
    when it does. `None` means the variable, if any, came from the environment the process was started with.
    """
    working_env_path = Path(WORKING_DIRECTORY_ENV_FILE_NAME).resolve()
    home_env_path = get_global_env_path()
    for env_path in (working_env_path, home_env_path):
        if env_path.is_file() and dotenv_values(env_path).get(PIPELEX_BASE_URL_ENV_KEY) is not None:
            return env_path
    return None


def read_saved_pipelex_api_key() -> str | None:
    """The key saved in the home `.env`, or `None` when it holds none."""
    return read_env_file_value(env_path=get_global_env_path(), key=PIPELEX_API_KEY_ENV_KEY)


def find_pipelex_api_key() -> str | None:
    """The key a hosted run would use: `PIPELEX_API_KEY` in the environment, else the one saved in the home `.env`.

    A variable present in the environment decides, even when empty: an empty value is what the next process sends, so it
    is no key, and the saved one is not looked at. The runtime loads the home `.env` into the environment at import, so
    the saved key only matters when the file was written after that, or under a `PIPELEX_HOME` set since.
    """
    if PIPELEX_API_KEY_ENV_KEY in os.environ:
        return os.environ[PIPELEX_API_KEY_ENV_KEY] or None
    return read_saved_pipelex_api_key()


class ShadowingEnvFile(NamedTuple):
    """The working directory's `.env`, when its `PIPELEX_API_KEY` line overrides the saved key."""

    path: Path
    #: Whether it sets the variable to an empty value, rather than to another key.
    sets_empty_value: bool


def find_shadowing_env_file() -> ShadowingEnvFile | None:
    """The working directory's `.env` when it sets `PIPELEX_API_KEY` to something other than the key saved in the home `.env`.

    The runtime loads that file after the home one, both overriding, so its value, an empty one included, is what every
    command run in this directory sends. A key set there alone, with none saved, is that directory's key and shadows
    nothing. Neither value is returned.
    """
    working_env_path = Path(WORKING_DIRECTORY_ENV_FILE_NAME).resolve()
    if not working_env_path.is_file() or working_env_path == get_global_env_path().resolve():
        return None
    values = dotenv_values(working_env_path)
    if PIPELEX_API_KEY_ENV_KEY not in values:
        return None
    working_value = values[PIPELEX_API_KEY_ENV_KEY] or ""
    saved_key = read_saved_pipelex_api_key()
    if working_value and (saved_key is None or working_value == saved_key):
        return None
    return ShadowingEnvFile(path=working_env_path, sets_empty_value=not working_value)
