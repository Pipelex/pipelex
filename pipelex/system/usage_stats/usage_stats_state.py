"""The shared state every reporting tool on a machine reads and writes, `~/.mthds/usage-stats/`.

One small file per fact, each created or deleted whole and never rewritten, so two tools running at once can never
undo each other's choice: `id` holds the installation identifier, published with a hard link so that racing first runs
converge on one; `disabled` turns statistics off for every tool; `legacy-migrated` records when the legacy `mthds`
opt-out was last carried over; `notice-v<N>` records that notice N was shown; `internal` marks a team machine; and
`spool/<tool>/` queues each tool's unsent events. The contract is `conformance/specs/usage-statistics.md`, "Shared state".

Standard library only, for the reason `usage_stats_contract` gives. A filesystem failure is never raised from a reader:
statistics are a measurement, never part of what the person asked for, so an unreadable state reads as absent.
"""

import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import NamedTuple

from pipelex.system.usage_stats.usage_stats_contract import (
    DISABLED_FILE_NAME,
    ID_FILE_NAME,
    ID_STALE_TEMP_MINUTES,
    INSTALLATION_ID_PATTERN,
    INTERNAL_FILE_NAME,
    LEGACY_CONFIG_PARTS,
    LEGACY_DISABLE_ON_VALUES,
    LEGACY_KEY,
    LEGACY_MIGRATED_FILE_NAME,
    NOTICE_FILE_PREFIX,
    SPOOL_DIR_NAME,
    SPOOL_TOOLS,
    STATE_DIR_PARTS,
)

_INSTALLATION_ID = re.compile(INSTALLATION_ID_PATTERN)
_ID_TEMP_PREFIX = f"{ID_FILE_NAME}.tmp-"
_STATE_DIR_MODE = 0o700


class InstallationId(NamedTuple):
    """The identifier a process sends under, and whether this process created it or drew it for itself alone."""

    value: str
    is_new: bool


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
        except OSError:
            return False
        return self.state_dir.is_dir()

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
            temporary.unlink(missing_ok=True)
            return process_local

        published: bool
        try:
            os.link(temporary, self.id_file)
            published = True
        except FileExistsError:
            published = False
        except OSError:
            # A filesystem without hard links, or one that refuses them here: nothing is persisted.
            temporary.unlink(missing_ok=True)
            return process_local
        temporary.unlink(missing_ok=True)

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
        return self.disabled_file.exists()

    def is_internal(self) -> bool:
        return self.internal_file.exists()

    def seen_notice_version(self, *, up_to: int) -> int:
        """The highest notice version N, no higher than `up_to`, for which `notice-v<N>` exists, and 0 when none does."""
        for version in range(up_to, 0, -1):
            if self.notice_marker(version=version).exists():
                return version
        return 0

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
