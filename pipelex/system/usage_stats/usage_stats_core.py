"""The self-contained core of pipelex's usage statistics: the shared state, the spool, the post, and the detached sender.

Everything a sender needs lives here, and nothing else does, because a CLI command starts this very file as its
detached sender: `python -I <path of this file> --home <home> --origin <origin> --tool pipelex`. Isolated mode keeps the
interpreter away from the environment's `PYTHON*` variables, the user's site-packages and the current directory, and a
file started by path imports none of the modules beside it, so this module imports the standard library and nothing
else, and never the `pipelex` package: the sender then delivers whether pipelex is installed for the user, through
`PYTHONPATH`, or in a virtual environment the sender's interpreter does not see, and it starts without loading pipelex.
The rest of the package imports what it needs from here, so the in-process paths and the sender run one code.

- **The shared state**, `~/.mthds/usage-stats/`: one small file per fact, each created or deleted whole and never
  rewritten, so two tools running at once can never undo each other's choice. `id` holds the installation identifier,
  published with a hard link so that racing first runs converge on one; `disabled` turns statistics off for every
  tool; `legacy-migrated` records when the legacy `mthds` opt-out was last carried over; `notice-v<N>` records that
  notice N was shown; `internal` marks a team machine; and `spool/<tool>/` queues each tool's unsent events. A
  filesystem failure is never raised from a reader: statistics are a measurement, never part of what the person asked
  for, so an unreadable state reads as absent, except `disabled`, which it may hold: statistics are then off.
- **The spool**: a file is named `<created-ms>-<random>.json` and holds `{"spool_version": 1, "events": [...]}`, to
  which pipelex adds `"endpoint"`, the origin the events were queued for: a sender posts a file only to that origin,
  and a file naming none, as the contract's shape names none, to any. It is written under a name starting with a dot
  and renamed into place, so a reader never sees it partial, and readers ignore names starting with a dot. A sender
  claims a file by renaming it to `<name>.sending-<random>`, so two senders never post one file, and after its attempt
  deletes it or renames it back.
- **The post**: `POST <origin>/batch/` with `{"api_key": <project token>, "batch": [...]}` and nothing else, so no SDK
  library property, no `sent_at`. Redirects are never followed, so a batch can never be carried anywhere but the
  origin it was addressed to, and a loopback origin is reached without a proxy. A post returns within the time left in
  its budget whatever the network does, name resolution included.
- **The checks before each post**: the legacy migration runs, nothing is sent when `disabled` exists or when a legacy
  opt-out the migration could not carry over is still pending, and every event whose `distinct_id` is not the current
  identifier is dropped, since it was made under one `reset-id` has replaced.

The contract is `conformance/specs/usage-statistics.md`, "Shared state" and "Delivery"; the constants here are checked
against its schema by the tests, beside the ones of `usage_stats_contract`.
"""

import argparse
import http.client
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.request
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple, cast

# -------------------------------------------------------------------------------------------------
# The contract's facts a sender needs
# -------------------------------------------------------------------------------------------------

CAPTURE_HOST = "https://eu.i.posthog.com"
BATCH_PATH = "/batch/"
#: The project's ingestion token. It is public by design: it can only write events, and the gate decides what is kept.
PROJECT_TOKEN = "phc_uQjSVbzNPJxA8bHxfevn7NMzB6PbC6aJQRB6ka6MxT7a"
#: Responses after which a sender deletes what it posted, since a resend would be refused again.
PERMANENT_REFUSAL_STATUSES: frozenset[int] = frozenset({400, 401, 403, 413})

#: The shared state directory, under the home directory.
STATE_DIR_PARTS: tuple[str, ...] = (".mthds", "usage-stats")
ID_FILE_NAME = "id"
DISABLED_FILE_NAME = "disabled"
LEGACY_MIGRATED_FILE_NAME = "legacy-migrated"
NOTICE_FILE_PREFIX = "notice-v"
INTERNAL_FILE_NAME = "internal"
SPOOL_DIR_NAME = "spool"
#: Today's `mthds` CLI configuration, under the home directory, the key its opt-out is stored under, and the values meaning off.
LEGACY_CONFIG_PARTS: tuple[str, ...] = (".mthds", "config")
LEGACY_KEY = "DISABLE_TELEMETRY"
LEGACY_DISABLE_ON_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})
#: Every tool's spool directory, which `disable`, `reset-id` and the legacy migration empty.
SPOOL_TOOLS: tuple[str, ...] = ("pipelex", "plxt", "vscode-pipelex", "mthds")

SPOOL_VERSION = 1
SPOOL_MAX_FILES_PER_TOOL = 100
SPOOL_MAX_AGE_DAYS = 30
SPOOL_STALE_CLAIM_MINUTES = 10
SPOOL_STALE_TEMP_MINUTES = 60
#: A temporary identifier file older than this is a crashed writer's leftover, which any tool may delete.
ID_STALE_TEMP_MINUTES = 60

BUDGET_CLI_IN_PROCESS_MS = 1000
BUDGET_PYTHON_EXIT_FLUSH_MS = 250
BUDGET_SHUTDOWN_FLUSH_MS = 2000
BUDGET_DETACHED_SENDER_MS = 10000
BUDGET_BACKGROUND_POST_DELAY_MS = 10000

INSTALLATION_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"

#: Below this many seconds left in a budget, a sender does not start a request it could not finish.
MINIMUM_REQUEST_SECONDS = 0.05

#: A loopback `http` origin with a port and no path: the only endpoint override the contract accepts.
_LOOPBACK_ORIGIN = re.compile(r"^http://(127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})$")


def is_loopback_origin(*, origin: str) -> bool:
    """Whether `origin` is `http://127.0.0.1:<port>`, `http://localhost:<port>` or `http://[::1]:<port>`, with no path."""
    match = _LOOPBACK_ORIGIN.fullmatch(origin)
    if match is None:
        return False
    port = int(match.group(2))
    return 0 < port < 65536


def is_allowed_origin(*, origin: str) -> bool:
    """Whether events may be posted to `origin`: the project's capture host, or the machine itself."""
    return origin == CAPTURE_HOST or is_loopback_origin(origin=origin)


# -------------------------------------------------------------------------------------------------
# The shared state
# -------------------------------------------------------------------------------------------------

_INSTALLATION_ID = re.compile(INSTALLATION_ID_PATTERN)
_ID_TEMP_PREFIX = f"{ID_FILE_NAME}.tmp-"
_STATE_DIR_MODE = 0o700


class InstallationId(NamedTuple):
    """The identifier a process sends under, and whether this process created it or drew it for itself alone."""

    value: str
    is_new: bool


def path_exists(*, path: Path) -> bool | None:
    """Whether `path` exists, and `None` when that cannot be told, as when a directory above it may not be traversed.

    It stats the path itself rather than asking `Path.exists()`, which from Python 3.14 swallows every `OSError` and
    answers `False`, so a `disabled` file in a state that cannot be looked into would read as absent.
    """
    try:
        path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return None
    return True


def delete_file(*, path: Path) -> None:
    """Delete `path` if it exists; a file that cannot be deleted stays, and is met again by whoever looks next."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def new_installation_id() -> str:
    """A random UUID version 4 in its canonical lowercase form, derived from nothing about the machine or the person."""
    return str(uuid.uuid4())


def is_installation_id(*, value: str) -> bool:
    return _INSTALLATION_ID.fullmatch(value) is not None


def parse_legacy_config(*, content: str) -> dict[str, str]:
    """Parse `~/.mthds/config` in the dialect of `conformance/specs/mthds-config-file.md`.

    Lines split on newline characters only, each trimmed; blank lines and whole-line `#` comments are skipped, as is a
    line with no `=`; the key is left of the first `=` and the value right of it, both trimmed; a later duplicate key wins.
    """
    entries: dict[str, str] = {}
    for raw_line in content.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        entries[key.strip()] = value.strip()
    return entries


class UsageStatsState:
    """The shared state directory under one home directory, and every operation the contract makes on it."""

    def __init__(self, *, home: Path) -> None:
        self.home = home
        self.state_dir = home.joinpath(*STATE_DIR_PARTS)
        self.id_file = self.state_dir / ID_FILE_NAME
        self.disabled_file = self.state_dir / DISABLED_FILE_NAME
        self.legacy_marker = self.state_dir / LEGACY_MIGRATED_FILE_NAME
        self.internal_file = self.state_dir / INTERNAL_FILE_NAME
        self.spool_root = self.state_dir / SPOOL_DIR_NAME
        self.legacy_config = home.joinpath(*LEGACY_CONFIG_PARTS)

    @classmethod
    def make_for_current_home(cls) -> "UsageStatsState":
        """The state under this user's home directory: `$HOME` on POSIX, `%USERPROFILE%` on Windows."""
        return cls(home=Path.home())

    def spool_dir(self, *, tool: str) -> Path:
        return self.spool_root / tool

    def notice_marker(self, *, version: int) -> Path:
        return self.state_dir / f"{NOTICE_FILE_PREFIX}{version}"

    def ensure_state_dir(self) -> bool:
        """Create the directory, mode 0700, when a tool first needs it; whether it exists now."""
        try:
            self.state_dir.mkdir(mode=_STATE_DIR_MODE, parents=True, exist_ok=True)
            return self.state_dir.is_dir()
        except OSError:
            return False

    # ---------------------------------------------------------------------------------------------
    # The installation identifier
    # ---------------------------------------------------------------------------------------------

    def read_installation_id(self) -> str | None:
        """The identifier `id` holds, surrounding whitespace removed, or `None` when it is absent, unreadable or malformed."""
        try:
            content = self.id_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        candidate = content.strip()
        return candidate if is_installation_id(value=candidate) else None

    def obtain_installation_id(self) -> InstallationId:
        """The identifier this process sends under, creating `id` when it does not exist.

        A fresh identifier is written, with no newline, to `id.tmp-<random>`, flushed to disk and published with a hard
        link to `id`, which fails when `id` exists; the temporary file is deleted either way. When the link fails because
        `id` exists, the identifier it holds is used, so racing first runs converge on one and exactly one of them reports
        it as new. When no link can be made at all, the directory is not writable, or `id` exists but is malformed, the
        process uses its fresh identifier for itself alone and persists nothing; a malformed `id` is never rewritten.
        """
        fresh_id = new_installation_id()
        process_local = InstallationId(value=fresh_id, is_new=True)
        try:
            existing = self.id_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            existing = None
        except (OSError, UnicodeDecodeError):
            return process_local
        if existing is not None:
            candidate = existing.strip()
            return InstallationId(value=candidate, is_new=False) if is_installation_id(value=candidate) else process_local

        if not self.ensure_state_dir():
            return process_local
        self._delete_stale_id_temps()
        temporary = self.state_dir / f"{_ID_TEMP_PREFIX}{secrets.token_hex(6)}"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(descriptor, fresh_id.encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            delete_file(path=temporary)
            return process_local

        published: bool
        try:
            os.link(temporary, self.id_file)
            published = True
        except FileExistsError:
            published = False
        except OSError:
            # A filesystem without hard links, or one that refuses them here: nothing is persisted.
            delete_file(path=temporary)
            return process_local
        delete_file(path=temporary)

        if published:
            return InstallationId(value=fresh_id, is_new=True)
        winner = self.read_installation_id()
        return InstallationId(value=winner, is_new=False) if winner is not None else process_local

    def replace_installation_id(self) -> str:
        """`reset-id`: delete every tool's spool and `id`, then create a new identifier and return it.

        Raises:
            OSError: when the new identifier could not be persisted, so `reset-id` can say it did not do what it says.
        """
        self.delete_every_spool()
        self.id_file.unlink(missing_ok=True)
        installation_id = self.obtain_installation_id()
        if self.read_installation_id() != installation_id.value:
            msg = f"The new installation identifier could not be written to {self.id_file}"
            raise OSError(msg)
        return installation_id.value

    def _delete_stale_id_temps(self) -> None:
        """Delete `id.tmp-*` files older than an hour, the leftovers of a writer that crashed."""
        threshold = time.time() - ID_STALE_TEMP_MINUTES * 60
        try:
            candidates = [entry for entry in self.state_dir.iterdir() if entry.name.startswith(_ID_TEMP_PREFIX)]
        except OSError:
            return
        for candidate in candidates:
            try:
                if candidate.stat().st_mtime < threshold:
                    candidate.unlink(missing_ok=True)
            except OSError:
                continue

    # ---------------------------------------------------------------------------------------------
    # The facts
    # ---------------------------------------------------------------------------------------------

    def is_disabled(self) -> bool:
        """Whether `disabled` exists; a state that cannot be looked into fails closed, since it may hold that choice."""
        return path_exists(path=self.disabled_file) is not False

    def is_internal(self) -> bool:
        return path_exists(path=self.internal_file) is True

    def seen_notice_version(self, *, up_to: int) -> int:
        """The highest notice version N, no higher than `up_to`, for which `notice-v<N>` exists, and 0 when none does."""
        for version in range(up_to, 0, -1):
            if path_exists(path=self.notice_marker(version=version)) is True:
                return version
        return 0

    def notice_was_recorded(self, *, version: int) -> bool:
        """Whether `notice-v<version>` exists; a marker that cannot be looked for is absent, so the notice is printed."""
        return path_exists(path=self.notice_marker(version=version)) is True

    def record_notice(self, *, version: int) -> bool:
        """Create `notice-v<version>`; whether it exists now. A notice that cannot be recorded is shown again next time."""
        if not self.ensure_state_dir():
            return False
        try:
            self.notice_marker(version=version).touch(exist_ok=True)
        except OSError:
            return False
        return True

    def disable(self) -> None:
        """`disable`: create `disabled` and delete every spooled file of every tool.

        Raises:
            OSError: when `disabled` could not be created.
        """
        self.state_dir.mkdir(mode=_STATE_DIR_MODE, parents=True, exist_ok=True)
        self.disabled_file.touch(exist_ok=True)
        self.delete_every_spool()

    def enable(self) -> None:
        """`enable`: delete `disabled`, and set `legacy-migrated` so the legacy opt-out already carried over is not migrated again.

        Raises:
            OSError: when `disabled` could not be deleted or the marker could not be set.
        """
        self.disabled_file.unlink(missing_ok=True)
        self.state_dir.mkdir(mode=_STATE_DIR_MODE, parents=True, exist_ok=True)
        self._set_legacy_marker()

    def delete_every_spool(self) -> None:
        """Delete every spooled file of every tool, claimed and temporary ones included; what cannot be deleted stays."""
        for tool in SPOOL_TOOLS:
            spool_dir = self.spool_dir(tool=tool)
            try:
                entries = list(spool_dir.iterdir())
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.is_file():
                        entry.unlink(missing_ok=True)
                except OSError:
                    continue

    # ---------------------------------------------------------------------------------------------
    # The legacy `mthds` opt-out
    # ---------------------------------------------------------------------------------------------

    def legacy_opt_out_is_on(self) -> bool:
        """Whether `DISABLE_TELEMETRY` in `~/.mthds/config` says off, read in that file's dialect."""
        try:
            content = self.legacy_config.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        value = parse_legacy_config(content=content).get(LEGACY_KEY)
        return value is not None and value.lower() in LEGACY_DISABLE_ON_VALUES

    def legacy_opt_out_is_pending(self) -> bool:
        """Whether the legacy opt-out says off and was written after it was last migrated (or was never migrated)."""
        if not self.legacy_opt_out_is_on():
            return False
        try:
            config_mtime_ns = self.legacy_config.stat().st_mtime_ns
        except OSError:
            return False
        try:
            marker_mtime_ns = self.legacy_marker.stat().st_mtime_ns
        except OSError:
            return True
        return config_mtime_ns > marker_mtime_ns

    def migrate_legacy_opt_out(self) -> None:
        """Carry a pending legacy opt-out into the shared state: create `disabled`, delete every spool, set the marker.

        Run by every reporting process before it reads any other switch, and by every sender before each post. A legacy
        value that does not mean off migrates nothing and writes nothing. A state that cannot be written leaves the legacy
        opt-out pending, so it still turns statistics off as the `legacy_mthds_choice` switch.
        """
        if not self.legacy_opt_out_is_pending():
            return
        try:
            self.disable()
            self._set_legacy_marker()
        except OSError:
            return

    def _set_legacy_marker(self) -> None:
        """Create `legacy-migrated` and set its modification time to the later of now and the legacy config's."""
        try:
            config_mtime_ns = self.legacy_config.stat().st_mtime_ns
        except OSError:
            config_mtime_ns = 0
        marker_ns = max(time.time_ns(), config_mtime_ns)
        self.legacy_marker.touch(exist_ok=True)
        os.utime(self.legacy_marker, ns=(marker_ns, marker_ns))


# -------------------------------------------------------------------------------------------------
# The spool
# -------------------------------------------------------------------------------------------------

SPOOL_FILE_SUFFIX = ".json"
#: The key under which pipelex records the endpoint a file's events were queued for, beside the contract's two.
SPOOL_ENDPOINT_KEY = "endpoint"
CLAIM_MARKER = ".sending-"
_TEMP_PREFIX = ".tmp-"


def _created_ms(*, path: Path) -> int | None:
    """The creation time a spool file's name starts with, or `None` for a name that is not a spool file's."""
    prefix = path.name.split("-", 1)[0]
    return int(prefix) if prefix.isdigit() else None


def is_pending(*, path: Path) -> bool:
    """Whether `path` is a spool file waiting for a sender: not temporary, not claimed."""
    name = path.name
    return not name.startswith(".") and CLAIM_MARKER not in name and name.endswith(SPOOL_FILE_SUFFIX) and _created_ms(path=path) is not None


def pending_files(*, spool_dir: Path) -> list[Path]:
    """The files waiting in `spool_dir`, oldest first."""
    try:
        entries = [entry for entry in spool_dir.iterdir() if is_pending(path=entry)]
    except OSError:
        return []
    return sorted(entries, key=lambda entry: (_created_ms(path=entry) or 0, entry.name))


class SpoolContent(NamedTuple):
    """What a spool file holds: the endpoint its events were queued for, when it names one, and the events."""

    endpoint: str | None
    events: list[dict[str, Any]]

    def is_queued_for(self, *, origin: str) -> bool:
        """Whether a sender posting to `origin` may post these events: the file names that endpoint, or names none."""
        return self.endpoint is None or self.endpoint == origin


def _spool_payload(*, content: SpoolContent) -> str:
    payload: dict[str, Any] = {"spool_version": SPOOL_VERSION}
    if content.endpoint is not None:
        payload[SPOOL_ENDPOINT_KEY] = content.endpoint
    payload["events"] = content.events
    return json.dumps(payload)


def write_spool_file(*, spool_dir: Path, content: SpoolContent) -> Path:
    """Queue events in a new file, then keep at most the contract's number of files, deleting the oldest.

    Raises:
        OSError: when the file could not be written.
    """
    spool_dir.mkdir(parents=True, exist_ok=True)
    final_path = spool_dir / f"{int(time.time() * 1000)}-{secrets.token_hex(6)}{SPOOL_FILE_SUFFIX}"
    temporary = spool_dir / f"{_TEMP_PREFIX}{secrets.token_hex(6)}"
    try:
        temporary.write_text(_spool_payload(content=content), encoding="utf-8")
        temporary.rename(final_path)
    finally:
        temporary.unlink(missing_ok=True)
    _enforce_file_limit(spool_dir=spool_dir)
    return final_path


def _enforce_file_limit(*, spool_dir: Path) -> None:
    waiting = pending_files(spool_dir=spool_dir)
    for oldest in waiting[: max(0, len(waiting) - SPOOL_MAX_FILES_PER_TOOL)]:
        delete_file(path=oldest)


def read_spool_file(*, path: Path) -> SpoolContent | None:
    """What a spool file holds, or `None` for a file that is not one: unreadable, not JSON, or of another shape."""
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    payload_dict = cast("dict[str, Any]", payload)
    events: object = payload_dict.get("events")
    endpoint: object = payload_dict.get(SPOOL_ENDPOINT_KEY)
    if payload_dict.get("spool_version") != SPOOL_VERSION or not isinstance(events, list):
        return None
    if endpoint is not None and not isinstance(endpoint, str):
        return None
    event_list = cast("list[object]", events)
    if not all(isinstance(event, dict) for event in event_list):
        return None
    return SpoolContent(endpoint=endpoint, events=cast("list[dict[str, Any]]", event_list))


def rewrite_spool_file(*, path: Path, content: SpoolContent) -> None:
    """Replace what a file this sender has claimed holds, as a whole.

    Raises:
        OSError: when the file could not be replaced.
    """
    temporary = path.parent / f"{_TEMP_PREFIX}{secrets.token_hex(6)}"
    try:
        temporary.write_text(_spool_payload(content=content), encoding="utf-8")
        Path(temporary).replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def claim(*, path: Path) -> Path | None:
    """Claim a waiting file for this sender, or `None` when another sender took it first.

    The claim's modification time is set to now, so a claim's age is how long its sender has held it.
    """
    claimed = path.with_name(f"{path.name}{CLAIM_MARKER}{secrets.token_hex(6)}")
    try:
        path.rename(claimed)
    except OSError:
        return None
    try:
        os.utime(claimed)
    except OSError:
        # The claim stands without its fresh time: it can only look stale sooner, and be resent, never be lost.
        return claimed
    return claimed


def release(*, claimed: Path) -> None:
    """Give a claimed file back for the next sender, under its name before the claim."""
    original = claimed.with_name(claimed.name.split(CLAIM_MARKER, 1)[0])
    try:
        claimed.rename(original)
    except OSError:
        return


def prune(*, spool_dir: Path) -> None:
    """Tidy a spool before draining it: give back stale claims, delete stale temporary files and files past their age."""
    now = time.time()
    try:
        entries = list(spool_dir.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            age_seconds = now - entry.stat().st_mtime
        except OSError:
            continue
        name = entry.name
        if name.startswith("."):
            if age_seconds > SPOOL_STALE_TEMP_MINUTES * 60:
                delete_file(path=entry)
        elif CLAIM_MARKER in name:
            if age_seconds > SPOOL_STALE_CLAIM_MINUTES * 60:
                release(claimed=entry)
        elif is_pending(path=entry):
            created_ms = _created_ms(path=entry) or 0
            if now * 1000 - created_ms > SPOOL_MAX_AGE_DAYS * 24 * 3600 * 1000:
                delete_file(path=entry)


# -------------------------------------------------------------------------------------------------
# The post
# -------------------------------------------------------------------------------------------------


class PostVerdict(StrEnum):
    """What a sender does with what it posted, by PostHog's answer."""

    ACCEPTED = "accepted"
    REFUSED = "refused"
    RETRY = "retry"

    @property
    def is_final(self) -> bool:
        """Whether the events are done with: accepted, or refused for good so a resend would be refused again."""
        match self:
            case PostVerdict.ACCEPTED | PostVerdict.REFUSED:
                return True
            case PostVerdict.RETRY:
                return False


def verdict_for_status(*, status: int) -> PostVerdict:
    if 200 <= status < 300:
        return PostVerdict.ACCEPTED
    if status in PERMANENT_REFUSAL_STATUSES:
        return PostVerdict.REFUSED
    return PostVerdict.RETRY


def _make_opener(*, origin: str) -> urllib.request.OpenerDirector:
    """An opener that follows no redirect and turns no status into an exception: the status is read as it came.

    A loopback origin is reached without a proxy; any other goes through the proxies the environment names.
    """
    opener = urllib.request.OpenerDirector()
    proxy_handler = urllib.request.ProxyHandler({}) if is_loopback_origin(origin=origin) else urllib.request.ProxyHandler()
    for handler in (proxy_handler, urllib.request.HTTPHandler(), urllib.request.HTTPSHandler()):
        opener.add_handler(handler)
    return opener


def _request_verdict(*, origin: str, events: list[dict[str, Any]], timeout_seconds: float, answers: list[PostVerdict]) -> None:
    """Make the request and append PostHog's answer to `answers`; any failure to get an answer is `RETRY`."""
    body = json.dumps({"api_key": PROJECT_TOKEN, "batch": events}).encode("utf-8")
    request = urllib.request.Request(  # ruff: ignore[suspicious-url-open-usage] — the origin is PostHog's capture host or a loopback override, both checked
        url=f"{origin.rstrip('/')}{BATCH_PATH}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        response = _make_opener(origin=origin).open(request, timeout=timeout_seconds)
        with response:
            status: int = response.status
    except (OSError, http.client.HTTPException, ValueError):
        # No answer at all: a network failure, a timeout, a connection closed mid-answer or an origin the opener refused.
        answers.append(PostVerdict.RETRY)
        return
    answers.append(verdict_for_status(status=status))


def post_batch(*, origin: str, events: list[dict[str, Any]], timeout_seconds: float) -> PostVerdict:
    """Post `events` in one request and return within `timeout_seconds`, whatever the network does.

    A socket's timeout bounds each of its operations, never name resolution nor the whole exchange, so a slow resolver
    or an answer trickling in byte by byte would hold the caller past its budget. The request runs on a daemon thread
    instead, which the caller waits for no longer than its budget: a request still running then is `RETRY`, and is left
    to finish or fail on its own. A resend carries the same `uuid`s, and PostHog keeps a single copy of each event.
    """
    if timeout_seconds < MINIMUM_REQUEST_SECONDS:
        return PostVerdict.RETRY
    answers: list[PostVerdict] = []
    request_thread = threading.Thread(
        target=_request_verdict,
        kwargs={"origin": origin, "events": events, "timeout_seconds": timeout_seconds, "answers": answers},
        name="pipelex-usage-stats-post",
        daemon=True,
    )
    try:
        request_thread.start()
    except RuntimeError:
        # The interpreter can start no thread: the events stay to be sent another time.
        return PostVerdict.RETRY
    request_thread.join(timeout=timeout_seconds)
    return answers[0] if answers else PostVerdict.RETRY


# -------------------------------------------------------------------------------------------------
# The checks before each post, and the drain
# -------------------------------------------------------------------------------------------------


def screen_events(*, state: UsageStatsState, events: list[dict[str, Any]], own_id: str | None) -> list[dict[str, Any]] | None:
    """The events still to send, checked immediately before a post; `None` when statistics were turned off since.

    Args:
        state: The shared state.
        events: The events about to be posted.
        own_id: The identifier this process sends under when `id` holds none it can read: a process-local identifier,
            whose events are this process's own and still to be sent. A detached sender has none.
    """
    state.migrate_legacy_opt_out()
    if state.is_disabled() or state.legacy_opt_out_is_pending():
        # A legacy opt-out the migration could not carry over still says off.
        return None
    current_id = state.read_installation_id() or own_id
    return [event for event in events if event.get("distinct_id") == current_id]


def send_claimed_file(*, state: UsageStatsState, claimed: Path, origin: str, deadline: float, own_id: str | None) -> PostVerdict | None:
    """Post a file this sender claimed, then delete it or give it back by PostHog's answer; `None` when nothing was posted."""
    content = read_spool_file(path=claimed)
    if content is None:
        delete_file(path=claimed)
        return None
    if not content.is_queued_for(origin=origin):
        release(claimed=claimed)
        return None
    events = content.events
    kept = screen_events(state=state, events=events, own_id=own_id)
    if not kept:
        delete_file(path=claimed)
        return None
    if len(kept) != len(events):
        try:
            rewrite_spool_file(path=claimed, content=content._replace(events=kept))
        except OSError:
            # The dropped events must never be sent: a file that cannot be rewritten without them is deleted with them.
            delete_file(path=claimed)
            return None
    verdict = post_batch(origin=origin, events=kept, timeout_seconds=deadline - time.monotonic())
    if verdict.is_final:
        delete_file(path=claimed)
    else:
        release(claimed=claimed)
    return verdict


def drain_spool(*, state: UsageStatsState, tool: str, origin: str, budget_ms: int) -> None:
    """Post the files of `tool`'s spool queued for `origin`, oldest first, within `budget_ms`, as the detached sender does."""
    drain_spool_until(state=state, tool=tool, origin=origin, deadline=time.monotonic() + budget_ms / 1000)


def drain_spool_until(*, state: UsageStatsState, tool: str, origin: str, deadline: float, first: Path | None = None) -> None:
    """Post the files of `tool`'s spool queued for `origin` until `deadline`: `first` when given, then the rest oldest first.

    A file queued for another endpoint is left for a sender posting there, so events queued under a test's loopback
    override never reach PostHog, and events queued for PostHog never reach a loopback endpoint. The events of each
    file are checked against the identifier `id` holds, so a process whose identifier is its own alone never drains.
    """
    spool_dir = state.spool_dir(tool=tool)
    prune(spool_dir=spool_dir)
    candidates = pending_files(spool_dir=spool_dir)
    if first is not None:
        candidates = [first, *(candidate for candidate in candidates if candidate != first)]
    for candidate in candidates:
        if time.monotonic() >= deadline:
            return
        content = read_spool_file(path=candidate)
        if content is not None and not content.is_queued_for(origin=origin):
            continue
        claimed = claim(path=candidate)
        if claimed is None:
            continue
        send_claimed_file(state=state, claimed=claimed, origin=origin, deadline=deadline, own_id=None)


def post_in_process(
    *, state: UsageStatsState, events: list[dict[str, Any]], origin: str, deadline: float, own_id: str | None
) -> tuple[PostVerdict | None, list[dict[str, Any]]]:
    """Post events held in memory after the checks; the verdict (`None` when nothing was posted) and the events posted."""
    kept = screen_events(state=state, events=events, own_id=own_id)
    if not kept:
        return None, []
    return post_batch(origin=origin, events=kept, timeout_seconds=deadline - time.monotonic()), kept


# -------------------------------------------------------------------------------------------------
# The detached sender
# -------------------------------------------------------------------------------------------------


def sender_command(*, executable: str, home: Path, origin: str, tool: str) -> list[str]:
    """The command line a CLI starts its detached sender with: this file, by path, in isolated mode."""
    return [executable, "-I", str(Path(__file__).resolve()), "--home", str(home), "--origin", origin, "--tool", tool]


def main(*, argv: list[str] | None = None) -> int:
    """Post every file of the tool's spool within the detached sender's budget, and exit.

    The origin was checked by the command that started this process; it is checked again here, so this file can never
    be made to post anywhere but the project or the machine itself.
    """
    parser = argparse.ArgumentParser(prog="pipelex-usage-stats-sender", add_help=False)
    parser.add_argument("--home", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--tool", required=True)
    arguments = parser.parse_args(argv)
    origin: str = arguments.origin
    tool: str = arguments.tool
    if not is_allowed_origin(origin=origin) or tool not in SPOOL_TOOLS:
        return 2
    drain_spool(state=UsageStatsState(home=Path(arguments.home)), tool=tool, origin=origin, budget_ms=BUDGET_DETACHED_SENDER_MS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
