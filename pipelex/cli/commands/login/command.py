"""`pipelex login`: get a Pipelex API key through the browser, or have one pasted, check it, and save it.

The browser flow opens the Pipelex app's `/auth/cli` page with the port of a one-shot loopback listener and a fresh
`state` value; the app mints a key for the signed-in account and sends the browser back to the listener with the key
and the same `state`. `--paste` takes a key created in the app instead, for a machine with no local browser. Either way
the key must start with `plx_sk_`, is checked against the hosted API (`GET /v1/me`), and is saved to the home `.env` as
`PIPELEX_API_KEY`: refused when the hosted API refuses it, saved with a warning when it could not be checked. The base
URL it was checked against is saved beside it when the file alone would pair it with another API. The key is never
printed.
"""

import webbrowser
from enum import StrEnum
from urllib.parse import urlencode, urlsplit

import typer
from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt

from pipelex.cli.commands.init.credentials import get_global_env_path
from pipelex.cli.commands.login.api_key_store import SavedApiKey, find_base_url_env_file, find_shadowing_env_file, save_pipelex_api_key
from pipelex.cli.commands.login.loopback import CallbackRefusal, LoopbackListener
from pipelex.cli.exceptions import PipelexCLIError
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.hosted.api_key_check import PIPELEX_API_KEY_PREFIX, ApiKeyVerdict, check_pipelex_api_key, is_well_formed_pipelex_api_key
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY, redact_url_for_display
from pipelex.runtime_hub import get_console
from pipelex.system.environment import get_optional_env
from pipelex.urls import URLs

#: How long the browser flow waits for the key: long enough to create an account on the way.
LOGIN_TIMEOUT_SECONDS = 300
#: The variable aiming `pipelex login` at another Pipelex app, such as a development one.
PIPELEX_APP_URL_ENV_KEY = "PIPELEX_APP_URL"
#: The app's page that mints a key for the command line.
CLI_AUTH_PATH = "/auth/cli"
#: The command that signs in through the browser.
LOGIN_COMMAND = "pipelex login"
#: The command for a machine with no local browser.
LOGIN_PASTE_COMMAND = "pipelex login --paste"


class KeySource(StrEnum):
    """Where the key a login checks came from."""

    #: The app minted it for this login and handed it back through the loopback listener.
    BROWSER = "browser"
    #: The person pasted a key they created in the app.
    PASTE = "paste"

    @property
    def is_minted_by_this_login(self) -> bool:
        """Whether this login made the key exist, so a key it does not save is a live key nobody holds."""
        match self:
            case KeySource.BROWSER:
                return True
            case KeySource.PASTE:
                return False

    @property
    def login_command(self) -> str:
        """The command that gets a key the same way again."""
        match self:
            case KeySource.BROWSER:
                return LOGIN_COMMAND
            case KeySource.PASTE:
                return LOGIN_PASTE_COMMAND


class LoginOutcome(StrEnum):
    """How a login ended."""

    SAVED = "saved"
    SAVED_UNCHECKED = "saved_unchecked"
    REFUSED = "refused"
    NO_KEY = "no_key"
    #: The key was good, but the home `.env` could not be written.
    NOT_SAVED = "not_saved"

    @property
    def is_saved(self) -> bool:
        match self:
            case LoginOutcome.SAVED | LoginOutcome.SAVED_UNCHECKED:
                return True
            case LoginOutcome.REFUSED | LoginOutcome.NO_KEY | LoginOutcome.NOT_SAVED:
                return False


def _is_origin(*, value: str) -> bool:
    """Whether a value is `scheme://host[:port]`, with http or https and no credentials, path, query or fragment."""
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return False
    has_credentials = parts.username is not None or parts.password is not None
    return not has_credentials and not (parts.path or parts.query or parts.fragment)


def resolve_app_origin() -> str:
    """The origin of the Pipelex app: `PIPELEX_APP_URL` when it is set, else https://app.pipelex.com.

    Raises:
        PipelexCLIError: If `PIPELEX_APP_URL` is set to something other than `scheme://host[:port]`.
    """
    configured = get_optional_env(PIPELEX_APP_URL_ENV_KEY)
    if configured is None:
        return URLs.app
    origin = configured.strip().rstrip("/")
    if not _is_origin(value=origin):
        msg = (
            f"{PIPELEX_APP_URL_ENV_KEY} is not an origin: {redact_url_for_display(url=configured)!r}. "
            f"Give scheme://host[:port], with http or https and no path, such as {URLs.app}, or unset it."
        )
        raise PipelexCLIError(msg).with_error_code(PipelexErrorCode.CONFIG_INVALID)
    return origin


def build_cli_auth_url(*, app_origin: str, callback_port: int, state: str) -> str:
    """The app page that mints a key and sends it back to the listener on `callback_port` with `state`."""
    query = urlencode({"callback_port": callback_port, "state": state})
    return f"{app_origin}{CLI_AUTH_PATH}?{query}"


def _unused_key_sentence(*, app_origin: str) -> str:
    """What a browser login says of a key the app minted for it and that it did not save."""
    return f"The key this login received went unused: revoke it on the Developer page of the Pipelex app ({escape(app_origin)})"


def _run_again(*, source: KeySource) -> str:
    """The end of an advice line: the command to run again, in the console's markup."""
    return f"[cyan]{source.login_command}[/cyan] [dim]again.[/dim]"


def _save_or_report(*, console: Console, api_key: str, checked_base_url: str | None, source: KeySource, app_origin: str) -> SavedApiKey | None:
    """Save the key to the home `.env`, or say why it could not be, never quoting the key.

    Returns:
        Where it was saved and what was saved beside it, or `None` when the file could not be written.
    """
    try:
        return save_pipelex_api_key(api_key=api_key, checked_base_url=checked_base_url)
    except OSError as exc:
        console.print(f"[red]The key could not be saved to {escape(str(get_global_env_path()))}: {escape(str(exc))}. Nothing was saved.[/red]")
        if source.is_minted_by_this_login:
            advice = f"{_unused_key_sentence(app_origin=app_origin)}, make that file writable, then run"
        else:
            advice = "The key you pasted was not saved: make that file writable, then run"
        console.print(f"[dim]{advice}[/dim] {_run_again(source=source)}")
        return None


def _describe_expected_api(*, shown_base_url: str) -> str:
    """The API a refused key had to belong to, saying where its base URL was set."""
    env_file = find_base_url_env_file()
    if env_file is not None:
        return f"the API the {PIPELEX_BASE_URL_ENV_KEY} in {escape(str(env_file))} names, {shown_base_url}"
    if get_optional_env(PIPELEX_BASE_URL_ENV_KEY) is not None:
        return f"the API {PIPELEX_BASE_URL_ENV_KEY} names, {shown_base_url}"
    return f"the hosted API, {shown_base_url}, used when {PIPELEX_BASE_URL_ENV_KEY} is not set"


def _saved_as(*, saved: SavedApiKey) -> str:
    """How the key was saved, for the line that says where."""
    if saved.saved_base_url is None:
        return f"as {PIPELEX_API_KEY_ENV_KEY}"
    return f"as {PIPELEX_API_KEY_ENV_KEY}, beside {PIPELEX_BASE_URL_ENV_KEY} for {escape(redact_url_for_display(url=saved.saved_base_url))}"


def _say_saved_base_url(*, console: Console, saved: SavedApiKey, source: KeySource) -> None:
    """Say what saving the base URL beside the key changes, or that it could not be saved."""
    if saved.saved_base_url is not None:
        console.print(
            f"[dim]{PIPELEX_BASE_URL_ENV_KEY} is saved with the key, so every command that loads {escape(str(saved.env_path))} "
            f"sends the key to {escape(redact_url_for_display(url=saved.saved_base_url))}, from any shell: the file wins over "
            f"a {PIPELEX_BASE_URL_ENV_KEY} your shell exports. Change or remove that line to use another API.[/dim]"
        )
    if saved.unsaved_base_url is not None:
        console.print(
            f"[yellow]⚠ The key was checked against {escape(redact_url_for_display(url=saved.unsaved_base_url))}, but "
            f"{PIPELEX_BASE_URL_ENV_KEY} could not be saved beside it: a .env file cannot hold that value unquoted, since it "
            "holds whitespace, a quote, #, $ or a backslash. A command that does not set it sends the key to another API: "
            f"correct {PIPELEX_BASE_URL_ENV_KEY}, then run {source.login_command} again.[/yellow]"
        )


def check_and_save_api_key(*, console: Console, api_key: str, source: KeySource, app_origin: str) -> LoginOutcome:
    """Check a key's format, then ask the hosted API about it, and save it unless it is malformed or refused.

    Args:
        console: Where to say what happened, never quoting the key.
        api_key: The key the browser handed back or the person pasted.
        source: Where the key came from, which decides whether a key left unsaved must be revoked.
        app_origin: The Pipelex app the key came from, where a key left unsaved is revoked.

    Returns:
        `SAVED` when the hosted API accepted it, `SAVED_UNCHECKED` when it could not be checked, `REFUSED` when it is
        not a Pipelex API key or the hosted API refused it, `NOT_SAVED` when the home `.env` could not be written
        (nothing is saved in those two cases).
    """
    api_key = api_key.strip()
    if not is_well_formed_pipelex_api_key(api_key=api_key):
        console.print(
            f"[red]That is not a Pipelex API key: a Pipelex API key starts with {PIPELEX_API_KEY_PREFIX} "
            "and holds no spaces or quotes. Nothing was saved.[/red]"
        )
        return LoginOutcome.REFUSED

    console.print("[dim]Checking the key with the hosted API…[/dim]")
    check = check_pipelex_api_key(api_key=api_key)
    shown_base_url = escape(redact_url_for_display(url=check.base_url))
    match check.verdict:
        case ApiKeyVerdict.REFUSED:
            console.print(f"[red]The hosted API at {shown_base_url} refused the key (HTTP {check.http_status}). Nothing was saved.[/red]")
            expected_api = _describe_expected_api(shown_base_url=shown_base_url)
            if source.is_minted_by_this_login:
                # The app minted the key for this login, so a refusal leaves a live key in the account that nobody holds.
                console.print(f"[dim]{_unused_key_sentence(app_origin=app_origin)}.[/dim]")
                advice = f"Check that the Pipelex app ({escape(app_origin)}) and {expected_api} belong to the same deployment, then run"
            else:
                advice = f"Check that the key is current and belongs to {expected_api}, then run"
            console.print(f"[dim]{advice}[/dim] {_run_again(source=source)}")
            return LoginOutcome.REFUSED
        case ApiKeyVerdict.ACCEPTED:
            saved = _save_or_report(console=console, api_key=api_key, checked_base_url=check.base_url or None, source=source, app_origin=app_origin)
            if saved is None:
                return LoginOutcome.NOT_SAVED
            account = f" as {escape(check.account_email)}" if check.account_email else ""
            console.print(
                f"[green]✓[/green] Logged in{account}. Your Pipelex API key is saved to {escape(str(saved.env_path))} {_saved_as(saved=saved)}."
            )
            _say_saved_base_url(console=console, saved=saved, source=source)
            warn_about_shadowing_env_file(console=console)
            return LoginOutcome.SAVED
        case ApiKeyVerdict.UNCHECKED:
            saved = _save_or_report(console=console, api_key=api_key, checked_base_url=check.base_url or None, source=source, app_origin=app_origin)
            if saved is None:
                return LoginOutcome.NOT_SAVED
            console.print(
                f"[yellow]⚠ Could not check the key: {escape(check.reason or 'no answer')}. "
                f"It is saved to {escape(str(saved.env_path))} {_saved_as(saved=saved)} anyway: "
                f"run {source.login_command} again if a hosted run refuses it.[/yellow]"
            )
            _say_saved_base_url(console=console, saved=saved, source=source)
            warn_about_shadowing_env_file(console=console)
            return LoginOutcome.SAVED_UNCHECKED


def warn_about_shadowing_env_file(*, console: Console) -> None:
    """Say so when the working directory's `.env` sets `PIPELEX_API_KEY` to something other than the saved key.

    The runtime loads that file after the home one, so commands run in this directory would send its value instead. Neither
    value is printed.
    """
    shadow = find_shadowing_env_file()
    if shadow is None:
        return
    what = "to an empty value" if shadow.sets_empty_value else "to another key"
    console.print(
        f"[yellow]⚠ {escape(str(shadow.path))} also sets {PIPELEX_API_KEY_ENV_KEY} ({what}) and is loaded after "
        f"{escape(str(get_global_env_path()))}, so commands run in this directory send that value instead. "
        f"Remove the {PIPELEX_API_KEY_ENV_KEY} line from it.[/yellow]"
    )


def _say_refusal(*, console: Console, refusal: CallbackRefusal) -> None:
    match refusal:
        case CallbackRefusal.STATE_MISMATCH:
            console.print("[yellow]Refused a sign-in that did not come from the page this login opened; still waiting.[/yellow]")
        case CallbackRefusal.NO_API_KEY:
            console.print("[yellow]A sign-in came back without an API key; still waiting.[/yellow]")


def login_with_browser(*, console: Console, timeout_seconds: float | None = None) -> LoginOutcome:
    """Open the app's key page in the browser, wait for the key on the loopback listener, then check and save it.

    Args:
        console: Where to print the link, the wait and the outcome.
        timeout_seconds: How long to wait for the browser; `LOGIN_TIMEOUT_SECONDS` when `None`.

    Returns:
        How the login ended; on `NO_KEY` the console names `pipelex login --paste`.
    """
    if timeout_seconds is None:
        timeout_seconds = LOGIN_TIMEOUT_SECONDS
    try:
        app_origin = resolve_app_origin()
    except PipelexCLIError as exc:
        console.print(f"[red]{escape(exc.message)}[/red]")
        return LoginOutcome.NO_KEY

    with LoopbackListener() as listener:
        auth_url = build_cli_auth_url(app_origin=app_origin, callback_port=listener.port, state=listener.state)
        console.print("[bold]Opening your browser to sign in to Pipelex…[/bold]")
        console.print(f"[dim]If it does not open, visit:[/dim] {escape(auth_url)}")
        if not webbrowser.open(auth_url):
            # The link is printed above, so a machine with no usable browser still has a way through.
            console.print(
                "[yellow]No browser could be opened here.[/yellow] Open the link above in a browser on this machine, "
                f"or press Ctrl-C and run [cyan]{LOGIN_PASTE_COMMAND}[/cyan]."
            )
        console.print(f"[dim]Waiting up to {int(timeout_seconds)} seconds for the key…[/dim]")
        api_key = listener.wait_for_api_key(
            timeout_seconds=timeout_seconds,
            on_refusal=lambda refusal: _say_refusal(console=console, refusal=refusal),
        )

    if api_key is None:
        console.print(f"[red]No key arrived within {int(timeout_seconds)} seconds.[/red]")
        console.print(
            f"[dim]Run[/dim] [cyan]pipelex login[/cyan] [dim]again, or create a key in the Pipelex app ({escape(app_origin)}) "
            f"and run[/dim] [cyan]{LOGIN_PASTE_COMMAND}[/cyan][dim].[/dim]"
        )
        return LoginOutcome.NO_KEY
    return check_and_save_api_key(console=console, api_key=api_key, source=KeySource.BROWSER, app_origin=app_origin)


def login_with_paste(*, console: Console) -> LoginOutcome:
    """Ask for a key created in the app, without echoing it, then check and save it.

    Returns:
        How the login ended: `NO_KEY` when nothing was pasted.
    """
    try:
        app_origin = resolve_app_origin()
    except PipelexCLIError as exc:
        console.print(f"[red]{escape(exc.message)}[/red]")
        return LoginOutcome.NO_KEY
    console.print(
        f"Paste a Pipelex API key ({PIPELEX_API_KEY_PREFIX}…) created in the Pipelex app ({escape(app_origin)}). It is not shown as you type."
    )
    try:
        api_key = Prompt.ask("[bold]Pipelex API key[/bold]", password=True, console=console, default="", show_default=False)
    except EOFError:
        api_key = ""
    if not api_key.strip():
        console.print("[red]No key was entered. Nothing was saved.[/red]")
        return LoginOutcome.NO_KEY
    return check_and_save_api_key(console=console, api_key=api_key, source=KeySource.PASTE, app_origin=app_origin)


def login_cmd(*, paste: bool = False) -> None:
    """Get a Pipelex API key, check it, and save it to the home `.env` as `PIPELEX_API_KEY`.

    Args:
        paste: Ask for a key created in the app instead of opening the browser.

    Raises:
        typer.Exit: With code 1 when no key was saved: none arrived, none was pasted, or it was malformed or refused.
    """
    console = get_console()
    console.print()
    outcome = login_with_paste(console=console) if paste else login_with_browser(console=console)
    console.print()
    if not outcome.is_saved:
        raise typer.Exit(code=1)
    # `pipelex init` would also make hosted runs the default, but it resets every configuration file: the one setting is lighter.
    home_pipelex_toml_path = get_global_env_path().parent / "pipelex.toml"
    console.print(
        "[dim]Run a method on the hosted API with[/dim] [cyan]pipelex run … --hosted[/cyan][dim], or make it the default by setting[/dim] "
        f'[cyan]\\[run] execution = "hosted"[/cyan] [dim]in {escape(str(home_pipelex_toml_path))}, '
        "or in a project's .pipelex/pipelex.toml.[/dim]"
    )
    console.print()
