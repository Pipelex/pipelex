"""The process's usage-statistics client: the switches it read, the events it holds, and how it delivers them.

A dedicated client, separate from the runtime's own telemetry (`TelemetryManager` and `telemetry.toml`), the user's
PostHog client and OpenTelemetry, all of which it never touches. One client per process:

- **A CLI command** (`pipelex`, `pipelex-agent`) configures it before the command does any work, which reads every
  switch and prints the notice; the command's events are held in memory and, when it ends, written to the spool for a
  detached sender (`usage_stats_core`, run by its file path), or posted in-process within one second in CI, in a
  container, or when the sender cannot start, followed within that second by what earlier commands queued.
- **A Python program, or a long-running process** such as the self-hosted API, configures it when it boots pipelex; a
  daemon thread posts events within ten seconds of their creation, and at exit (or at shutdown) what is left is flushed
  within the budget and spooled when it cannot be sent. Each time its events get through, what earlier processes
  queued goes too, within the same budget. Such a process never starts a child process.

With `PIPELEX_USAGE_STATS_DEBUG`, each event is printed on stderr as one JSON line instead, and nothing is sent or
spooled. The contract is `conformance/specs/usage-statistics.md`.
"""

import atexit
import json
import os
import sys
import threading
import time
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple

from pipelex import log
from pipelex.system.runtime import IntegrationMode
from pipelex.system.usage_stats.usage_stats_contract import (
    NOTICE_VERSION,
    TOOL_NAME,
    UsageStatsErrorDomain,
    UsageStatsHost,
    UsageStatsIntegration,
    UsageStatsOffBy,
    UsageStatsSurface,
    render_notice,
)
from pipelex.system.usage_stats.usage_stats_core import (
    BUDGET_BACKGROUND_POST_DELAY_MS,
    BUDGET_CLI_IN_PROCESS_MS,
    BUDGET_PYTHON_EXIT_FLUSH_MS,
    BUDGET_SHUTDOWN_FLUSH_MS,
    InstallationId,
    PostVerdict,
    SpoolContent,
    UsageStatsState,
    drain_spool_until,
    post_in_process,
    write_spool_file,
)
from pipelex.system.usage_stats.usage_stats_delivery import start_detached_sender
from pipelex.system.usage_stats.usage_stats_environment import (
    current_arch,
    current_language_runtime,
    current_os,
    declared_host,
    is_ci,
    is_container,
    is_debug,
    release_version,
    resolve_endpoint,
)
from pipelex.system.usage_stats.usage_stats_events import CommonProperties, InitChoices, UsageStatsEvent, make_envelope
from pipelex.system.usage_stats.usage_stats_switches import read_switches
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.misc.package_utils import get_package_version

#: How long the background thread waits after an event's creation for others to join its batch.
BACKGROUND_COALESCE_SECONDS = 1.0
#: The key each event printed under the debug variable is wrapped in.
DEBUG_KEY = "usage_stats_debug"


class UsageStatsDelivery(StrEnum):
    """How a process delivers its events."""

    CLI_COMMAND = "cli_command"
    PYTHON_PROGRAM = "python_program"
    LONG_RUNNING = "long_running"

    @property
    def flush_budget_ms(self) -> int:
        """The budget of the flush at exit or at shutdown."""
        match self:
            case UsageStatsDelivery.CLI_COMMAND:
                return BUDGET_CLI_IN_PROCESS_MS
            case UsageStatsDelivery.PYTHON_PROGRAM:
                return BUDGET_PYTHON_EXIT_FLUSH_MS
            case UsageStatsDelivery.LONG_RUNNING:
                return BUDGET_SHUTDOWN_FLUSH_MS


class UsageStatsSettings(NamedTuple):
    """What a process decided about its statistics before doing any work."""

    off_by: tuple[UsageStatsOffBy, ...]
    origin: str | None
    surface: UsageStatsSurface
    integration: UsageStatsIntegration
    host: UsageStatsHost | None
    delivery: UsageStatsDelivery
    is_debug: bool
    is_ci: bool
    is_container: bool
    state: UsageStatsState


def write_stderr_line(*, line: str) -> None:
    """Write one line to stderr; a stderr that is closed or broken loses the line and nothing else."""
    try:
        sys.stderr.write(f"{line}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        # A closed stream raises ValueError, a broken pipe OSError: the line is lost, the command is not.
        return


class _BackgroundSender:
    """The daemon thread of a Python program or a long-running process, posting events within ten seconds of their creation."""

    def __init__(self, *, settings: UsageStatsSettings, own_id: str) -> None:
        self._settings = settings
        self._own_id = own_id
        self._condition = threading.Condition()
        self._pending: list[tuple[float, dict[str, Any]]] = []
        self._in_flight: list[dict[str, Any]] = []
        self._thread: threading.Thread | None = None
        self._closed = False

    def enqueue(self, *, envelope: dict[str, Any]) -> None:
        with self._condition:
            if self._closed:
                self._spool(events=[envelope])
                return
            self._pending.append((time.monotonic(), envelope))
            if self._thread is None or not self._thread.is_alive():
                # The first event starts the thread, and a later one starts it again should it ever have ended.
                self._thread = threading.Thread(target=self._run, name="pipelex-usage-stats", daemon=True)
                self._thread.start()
            self._condition.notify_all()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                oldest_created = self._pending[0][0]
                still_to_wait = oldest_created + BACKGROUND_COALESCE_SECONDS - time.monotonic()
                if still_to_wait > 0:
                    self._condition.wait(timeout=still_to_wait)
                    continue
                batch = [envelope for _, envelope in self._pending]
                self._pending.clear()
                self._in_flight = batch
            deadline = oldest_created + BUDGET_BACKGROUND_POST_DELAY_MS / 1000
            try:
                self._post(events=batch, deadline=deadline)
            except (OSError, ValueError) as exc:
                # A filesystem failure no reader of the state absorbed (`OSError`), or a path or value the standard
                # library rejected (`ValueError`): the batch is lost, the thread lives on. Any other error is a bug,
                # which ends the thread with its traceback; `enqueue` starts a new one for the next event.
                log.debug("A usage statistics batch could not be posted", fields=error_fields(exc=exc))
            finally:
                with self._condition:
                    self._in_flight = []
                    self._condition.notify_all()

    def _post(self, *, events: list[dict[str, Any]], deadline: float) -> None:
        origin = self._settings.origin
        if origin is None:
            return
        state = self._settings.state
        verdict, posted = post_in_process(state=state, events=events, origin=origin, deadline=deadline, own_id=self._own_id)
        match verdict:
            case PostVerdict.RETRY:
                self._spool(events=posted)
            case PostVerdict.ACCEPTED:
                if state.read_installation_id() == self._own_id:
                    # PostHog accepted the batch, and this process sends under the machine's identifier: what earlier
                    # processes queued under it goes too, within what is left of the batch's budget.
                    drain_spool_until(state=state, tool=TOOL_NAME, origin=origin, deadline=deadline)
            case PostVerdict.REFUSED | None:
                # Refused for good, or nothing posted at all: nothing says PostHog would take what is queued.
                return

    def _spool(self, *, events: list[dict[str, Any]]) -> None:
        origin = self._settings.origin
        if not events or origin is None or self._settings.state.read_installation_id() != self._own_id:
            # A process-local identifier is this process's alone: its events are never persisted.
            return
        try:
            write_spool_file(spool_dir=self._settings.state.spool_dir(tool=TOOL_NAME), content=SpoolContent(endpoint=origin, events=events))
        except OSError:
            return

    def flush(self, *, budget_ms: int, close: bool) -> None:
        """Post what is pending within `budget_ms`, wait for a post in flight, and spool what is left."""
        deadline = time.monotonic() + budget_ms / 1000
        with self._condition:
            batch = [envelope for _, envelope in self._pending]
            self._pending.clear()
            if close:
                self._closed = True
                self._condition.notify_all()
        if batch:
            self._post(events=batch, deadline=deadline)
        with self._condition:
            self._condition.wait_for(lambda: not self._in_flight, timeout=max(0.0, deadline - time.monotonic()))
            unfinished = list(self._in_flight)
        if unfinished:
            # Spooled while its post may still land: a resend carries the same uuid, and PostHog keeps a single copy.
            self._spool(events=unfinished)


class UsageStatsClient:
    """The statistics of one process: whether they are on, the identifier its events carry, and where they go."""

    def __init__(self, *, settings: UsageStatsSettings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._installation_id: InstallationId | None = None
        self._common: CommonProperties | None = None
        self._held: list[dict[str, Any]] = []
        self._background: _BackgroundSender | None = None
        #: Who can fix the failure the command reported, when something said so; read for its `command_completed`.
        self.command_error_domain: UsageStatsErrorDomain | None = None
        #: Whether the command sent its work to the hosted API, which holds the rest of what it did.
        self.is_command_hosted = False
        #: What an `init` command set, for its `command_completed`.
        self.command_init_choices: InitChoices | None = None
        #: Whether this command printed the notice, which it then never prints a second time.
        self.is_notice_printed = False

    @property
    def is_enabled(self) -> bool:
        return not self.settings.off_by

    def note_command_error_domain(self, *, error_domain: UsageStatsErrorDomain) -> None:
        """Record who can fix the failure the command is reporting, as its error output classifies it; the last one wins."""
        self.command_error_domain = error_domain

    def note_command_hosted(self) -> None:
        """Record that the command sent its work to the hosted API, for its `command_completed`."""
        self.is_command_hosted = True

    def note_command_init_choices(self, *, init_choices: InitChoices) -> None:
        """Record what an `init` command set, for its `command_completed`; a later note completes an earlier one."""
        current = self.command_init_choices
        if current is None:
            self.command_init_choices = init_choices
            return
        self.command_init_choices = InitChoices(
            execution=init_choices.execution or current.execution,
            enabled_providers=init_choices.enabled_providers if init_choices.enabled_providers is not None else current.enabled_providers,
        )

    def reset_after_fork(self) -> None:
        """In a forked child: drop the parent's lock, its held events and its thread, which the child does not have."""
        self._lock = threading.Lock()
        self._held = []
        self._background = None

    def record(self, *, event: UsageStatsEvent) -> None:
        """Take one event: print it under the debug variable, hold it for the command's end, or hand it to the thread."""
        if not self.is_enabled:
            return
        try:
            envelope = self._make_envelope(event=event)
        except (OSError, ValueError):
            # A measurement that cannot be built is lost; the work it measures is not affected.
            return
        if self.settings.is_debug:
            write_stderr_line(line=json.dumps({DEBUG_KEY: envelope}))
            return
        match self.settings.delivery:
            case UsageStatsDelivery.CLI_COMMAND:
                with self._lock:
                    self._held.append(envelope)
            case UsageStatsDelivery.PYTHON_PROGRAM | UsageStatsDelivery.LONG_RUNNING:
                self._background_sender().enqueue(envelope=envelope)

    def _make_envelope(self, *, event: UsageStatsEvent) -> dict[str, Any]:
        with self._lock:
            installation_id = self._installation_id
            if installation_id is None:
                installation_id = self.settings.state.obtain_installation_id()
                self._installation_id = installation_id
            common = self._common
            if common is None:
                common = self._make_common_properties(installation_id=installation_id)
                self._common = common
        return make_envelope(event=event, distinct_id=installation_id.value, common=common)

    def _make_common_properties(self, *, installation_id: InstallationId) -> CommonProperties:
        settings = self.settings
        return CommonProperties(
            tool_version=release_version(version=get_package_version()),
            surface=settings.surface,
            integration=settings.integration,
            host=settings.host,
            id_new=installation_id.is_new,
            os=current_os(),
            arch=current_arch(),
            language_runtime=current_language_runtime(),
            ci=settings.is_ci,
            container=settings.is_container,
            internal=settings.state.is_internal(),
            notice_version=settings.state.seen_notice_version(up_to=NOTICE_VERSION),
        )

    def _background_sender(self) -> _BackgroundSender:
        with self._lock:
            if self._background is None:
                own_id = self._installation_id.value if self._installation_id is not None else ""
                self._background = _BackgroundSender(settings=self.settings, own_id=own_id)
                atexit.register(self._flush_at_exit)
            return self._background

    def _flush_at_exit(self) -> None:
        background = self._background
        if background is not None:
            background.flush(budget_ms=self.settings.delivery.flush_budget_ms, close=True)

    def flush(self) -> None:
        """Flush what the thread holds within the delivery's budget, as a long-running process does at shutdown."""
        background = self._background
        if background is not None:
            background.flush(budget_ms=self.settings.delivery.flush_budget_ms, close=False)

    def finish_command(self) -> None:
        """At a CLI command's end: spool its events and start the detached sender, or post them in-process."""
        with self._lock:
            events = list(self._held)
            self._held.clear()
            installation_id = self._installation_id
        origin = self.settings.origin
        if not events or origin is None or installation_id is None:
            return
        state = self.settings.state
        is_process_local = state.read_installation_id() != installation_id.value
        if self.settings.is_ci or self.settings.is_container or is_process_local:
            self._post_in_process(events=events, origin=origin, own_id=installation_id.value, may_spool=not is_process_local)
            return
        try:
            state.ensure_state_dir()
            spool_file = write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), content=SpoolContent(endpoint=origin, events=events))
        except OSError:
            self._post_in_process(events=events, origin=origin, own_id=installation_id.value, may_spool=False)
            return
        if start_detached_sender(state=state, origin=origin):
            return
        drain_spool_until(state=state, tool=TOOL_NAME, origin=origin, deadline=time.monotonic() + BUDGET_CLI_IN_PROCESS_MS / 1000, first=spool_file)

    def _post_in_process(self, *, events: list[dict[str, Any]], origin: str, own_id: str, may_spool: bool) -> None:
        """Post the command's events within its budget and, once PostHog accepted them, what earlier commands queued.

        Args:
            events: The command's events.
            origin: Where they go.
            own_id: The identifier they carry.
            may_spool: Whether this process sends under the machine's identifier and can write the spool: only then are
                its unsent events queued, and the events earlier processes queued sent.
        """
        state = self.settings.state
        deadline = time.monotonic() + BUDGET_CLI_IN_PROCESS_MS / 1000
        verdict, posted = post_in_process(state=state, events=events, origin=origin, deadline=deadline, own_id=own_id)
        if not may_spool:
            return
        match verdict:
            case PostVerdict.RETRY:
                try:
                    write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), content=SpoolContent(endpoint=origin, events=posted))
                except OSError:
                    return
            case PostVerdict.ACCEPTED:
                drain_spool_until(state=state, tool=TOOL_NAME, origin=origin, deadline=deadline)
            case PostVerdict.REFUSED | None:
                # Refused for good, or nothing posted at all: nothing says PostHog would take what is queued.
                return


# -------------------------------------------------------------------------------------------------
# The process's client
# -------------------------------------------------------------------------------------------------


class _ProcessUsageStats:
    """The process-wide state behind the module functions below."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.client: UsageStatsClient | None = None
        self.is_pytest = False
        self.embedder_host: UsageStatsHost | None = None
        self.runtime_notice_written = False
        #: Whether a CLI command decides this process's statistics, even when it could not configure them: booting
        #: pipelex inside the command then builds no client of its own.
        self.is_cli_command = False


_PROCESS = _ProcessUsageStats()


def _reset_after_fork() -> None:
    _PROCESS.lock = threading.Lock()
    client = _PROCESS.client
    if client is not None:
        client.reset_after_fork()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_after_fork)


def _integration_for(*, integration_mode: IntegrationMode) -> UsageStatsIntegration | None:
    """The `integration` property of a runtime integration mode; `None` for `pytest`, which turns statistics off."""
    match integration_mode:
        case IntegrationMode.CLI:
            return UsageStatsIntegration.CLI
        case IntegrationMode.PYTHON:
            return UsageStatsIntegration.PYTHON
        case IntegrationMode.FASTAPI:
            return UsageStatsIntegration.FASTAPI
        case IntegrationMode.DOCKER:
            return UsageStatsIntegration.DOCKER
        case IntegrationMode.MCP:
            return UsageStatsIntegration.MCP
        case IntegrationMode.N8N:
            return UsageStatsIntegration.N8N
        case IntegrationMode.CI:
            return UsageStatsIntegration.CI
        case IntegrationMode.PYTEST:
            return None


def _surface_and_delivery_for(*, integration: UsageStatsIntegration) -> tuple[UsageStatsSurface, UsageStatsDelivery]:
    """The surface and delivery of a process that booted pipelex itself rather than through a CLI command."""
    match integration:
        case UsageStatsIntegration.FASTAPI | UsageStatsIntegration.DOCKER:
            return UsageStatsSurface.API, UsageStatsDelivery.LONG_RUNNING
        case UsageStatsIntegration.MCP | UsageStatsIntegration.N8N:
            return UsageStatsSurface.PYTHON, UsageStatsDelivery.LONG_RUNNING
        case UsageStatsIntegration.CLI | UsageStatsIntegration.PYTHON | UsageStatsIntegration.CI:
            return UsageStatsSurface.PYTHON, UsageStatsDelivery.PYTHON_PROGRAM


def _current_dir() -> Path | None:
    try:
        return Path.cwd()
    except OSError:
        return None


def build_settings(
    *,
    state: UsageStatsState,
    env: Mapping[str, str],
    cwd: Path | None,
    is_pytest: bool,
    surface: UsageStatsSurface,
    integration: UsageStatsIntegration,
    delivery: UsageStatsDelivery,
    embedder_host: UsageStatsHost | None,
) -> UsageStatsSettings:
    """Run the legacy migration, then read every switch and the facts the process's events carry."""
    off_by: list[UsageStatsOffBy]
    if is_pytest:
        # No test suite reports, and none touches the machine's shared state to find that out.
        off_by = [UsageStatsOffBy.INTEGRATION_MODE]
    else:
        state.migrate_legacy_opt_out()
        off_by = read_switches(state=state, env=env, cwd=cwd or state.home, is_pytest=False)
    return UsageStatsSettings(
        off_by=tuple(off_by),
        origin=resolve_endpoint(env=env),
        surface=surface,
        integration=integration,
        host=embedder_host or declared_host(env=env),
        delivery=delivery,
        is_debug=is_debug(env=env),
        is_ci=is_ci(env=env),
        is_container=is_container(env=env),
        state=state,
    )


def configure_usage_stats_for_cli(*, surface: UsageStatsSurface, is_machine_read: bool) -> UsageStatsClient | None:
    """Read every switch for a CLI command about to run, and print the notice unless its stderr is read by a program.

    The notice goes to stderr before the command does any work, then `notice-v<N>` records it for every tool on the
    machine; a marker that cannot be written leaves the notice to be printed again next time. Where stderr is a machine
    contract, the notice is neither printed nor recorded, and the command's statistics are still sent.

    Returns:
        The command's client, or `None` when the switches could not be read at all, as when no home directory can be
        found: the command then runs without statistics, and pipelex booting inside it does not configure them again.
    """
    with _PROCESS.lock:
        _PROCESS.is_cli_command = True
    try:
        state = UsageStatsState.make_for_current_home()
        with _PROCESS.lock:
            settings = build_settings(
                state=state,
                env=os.environ,
                cwd=_current_dir(),
                is_pytest=_PROCESS.is_pytest,
                surface=surface,
                integration=UsageStatsIntegration.CLI,
                delivery=UsageStatsDelivery.CLI_COMMAND,
                embedder_host=_PROCESS.embedder_host,
            )
            client = UsageStatsClient(settings=settings)
            _PROCESS.client = client
    except (OSError, RuntimeError):
        # No home directory (`Path.home()` raises `RuntimeError`), or a filesystem failure no reader absorbed: the
        # command runs without statistics, which never stand in its way.
        return None
    if client.is_enabled and not is_machine_read and not state.notice_was_recorded(version=NOTICE_VERSION):
        write_stderr_line(line=render_notice())
        client.is_notice_printed = True
        state.record_notice(version=NOTICE_VERSION)
    return client


def show_usage_stats_notice() -> None:
    """Show the notice's text as part of a command's own output, as `pipelex init` does whenever statistics are on.

    The text goes to stderr, as the first-run notice does, and only when this command has not printed it already: a first
    run's notice stands for it. With statistics off, or switches that could not be read, nothing is shown. Showing the
    text records no `notice-v<N>` marker, and a marker already there does not stop it.
    """
    client = _PROCESS.client
    if client is None or not client.is_enabled or client.is_notice_printed:
        return
    write_stderr_line(line=render_notice())
    client.is_notice_printed = True


def configure_usage_stats_for_runtime(*, integration_mode: IntegrationMode) -> None:
    """Read every switch when a process boots pipelex, unless a CLI command decides them; `pytest` mode turns statistics off.

    A Python program or a long-running process writes the notice to stderr once per process, at startup, and records no
    marker, since nothing says a person reads that stream. Switches that cannot be read at all leave the process without
    statistics; booting pipelex never fails for them.
    """
    integration = _integration_for(integration_mode=integration_mode)
    with _PROCESS.lock:
        if integration is None:
            _PROCESS.is_pytest = True
            existing = _PROCESS.client
            if existing is not None and UsageStatsOffBy.INTEGRATION_MODE not in existing.settings.off_by:
                _PROCESS.client = UsageStatsClient(
                    settings=existing.settings._replace(off_by=(*existing.settings.off_by, UsageStatsOffBy.INTEGRATION_MODE))
                )
        if _PROCESS.client is not None or _PROCESS.is_cli_command:
            # A CLI command's client stands, and a command that could not configure one runs without statistics: a
            # program's client built now would print the runtime notice on a stderr the command may keep for JSON.
            return
        surface, delivery = _surface_and_delivery_for(integration=integration or UsageStatsIntegration.PYTHON)
        try:
            settings = build_settings(
                state=UsageStatsState.make_for_current_home(),
                env=os.environ,
                cwd=_current_dir(),
                is_pytest=_PROCESS.is_pytest,
                surface=surface,
                integration=integration or UsageStatsIntegration.PYTHON,
                delivery=delivery,
                embedder_host=_PROCESS.embedder_host,
            )
        except (OSError, RuntimeError):
            # No home directory, or a filesystem failure no reader absorbed: the process runs without statistics.
            return
        client = UsageStatsClient(settings=settings)
        _PROCESS.client = client
        write_notice = client.is_enabled and not _PROCESS.runtime_notice_written
        _PROCESS.runtime_notice_written = _PROCESS.runtime_notice_written or write_notice
    if write_notice:
        write_stderr_line(line=render_notice())


def declare_usage_stats_host(*, host: UsageStatsHost) -> None:
    """Declare the program of ours that embeds pipelex, such as `cocode`, before it boots pipelex."""
    with _PROCESS.lock:
        _PROCESS.embedder_host = host


def is_pytest_process() -> bool:
    """Whether this process booted pipelex in the `pytest` integration mode, which turns statistics off for good."""
    return _PROCESS.is_pytest


def get_usage_stats_client() -> UsageStatsClient | None:
    return _PROCESS.client


def usage_stats_are_enabled() -> bool:
    """Whether this process records events, so a caller can skip building one that would be dropped."""
    client = _PROCESS.client
    return client is not None and client.is_enabled


def record_usage_stats_event(*, event: UsageStatsEvent) -> None:
    """Record one event with the process's client; nothing happens when there is none or statistics are off."""
    client = _PROCESS.client
    if client is not None:
        client.record(event=event)


def note_command_error_domain(*, error_domain: UsageStatsErrorDomain) -> None:
    """Record, for the running command's `command_completed`, who can fix the failure it is reporting."""
    client = _PROCESS.client
    if client is not None:
        client.note_command_error_domain(error_domain=error_domain)


def note_command_hosted() -> None:
    """Record, for the running command's `command_completed`, that it sent its work to the hosted API."""
    client = _PROCESS.client
    if client is not None:
        client.note_command_hosted()


def note_command_init_choices(*, init_choices: InitChoices) -> None:
    """Record, for the running `init` command's `command_completed`, where it set runs to execute and which backends it enabled."""
    client = _PROCESS.client
    if client is not None:
        client.note_command_init_choices(init_choices=init_choices)


def flush_usage_stats() -> None:
    """Flush what the process's thread holds, within its delivery's budget, as a process shutting pipelex down does."""
    client = _PROCESS.client
    if client is not None:
        client.flush()


def reset_usage_stats_for_tests() -> None:
    """Forget the process's client and every decision it made, so a test configures its own."""
    with _PROCESS.lock:
        _PROCESS.client = None
        _PROCESS.is_pytest = False
        _PROCESS.embedder_host = None
        _PROCESS.runtime_notice_written = False
        _PROCESS.is_cli_command = False
