"""Helpers for structured output in agent CLI commands.

Two independent format axes:

- **Success output** is driven by the per-command ``--format`` Typer option, passed
  explicitly to :func:`agent_success_formatted`. No hidden state — every success
  call site lives inside a command function that has ``output_format`` in scope.
- **Error reporting** is driven by ``--error-format``, given to the command or before it to the
  program itself, else by the command's ``--format``. Errors must be format-aware from sites far
  from any Typer command (init failures in ``agent_cli_factory.py``, an unknown command from the
  Typer group, and so on), so the error format is carried in a module-level ``ContextVar``. JSON
  is the default so any error raised before a command opts in stays machine-parseable.

A failure is reported as a problem document (RFC 9457, the MTHDS core members and Pipelex's), in the operator's view,
since a local CLI is authenticated as the operator of the runtime it boots: its ``code``, ``domain``, ``retry`` and
``next_step`` are what an agent branches on, and ``diagnostics`` holds the error's class and message, the model and
provider of a failed call, and a pending configuration migration. The command's own sentence rides beside the core
members as ``message``, and a command's own facts (``is_valid``, ``bundle_path``, ``valid_commands`` and the like) as
further members. The JSON form is the problem as it is written on the wire; the Markdown form renders it for an agent
to read.

A hosted run's failure keeps the envelope it had before the problem, built from the hosted plane's answer
(:func:`agent_error_hosted_envelope`, :func:`agent_error_api_response`), until the hosted plane answers problems.
"""

import os
import sys
import traceback
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn, cast

import typer
from mthds.protocol.problem.models import ProblemItem, ProblemLocation
from mthds.protocol.problem.registry import CoreCode
from pipelex_sdk.errors import ApiResponseError
from pydantic import ValidationError

from pipelex.base_exceptions import ErrorDomain, PipelexError, ValidationErrorItem, iter_cause_chain, iter_pipelex_cause_chain
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.failure_problem import failure_diagnostics, failure_problem, format_problem_location, format_problem_verdict
from pipelex.errors.problem import (
    MigrationErrorBlock,
    PipelexProblem,
    ProblemDiagnostics,
    ProblemView,
    make_problem,
)
from pipelex.hosted.error_rendering import hosted_refusal_message, hosted_refusal_next_step, sent_verdict
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes.fix_loop import FixBundleResult
from pipelex.pipeline.fixes.fix_render import format_fix_progress_markdown
from pipelex.pipeline.validation_errors import problem_item_of
from pipelex.pipeline.validation_render import build_fix_command, count_applicable_fixes, format_validation_error_items_markdown
from pipelex.system.usage_stats.usage_stats_client import note_command_error
from pipelex.system.usage_stats.usage_stats_runs import sent_usage_stats_error, usage_stats_error, usage_stats_error_of_problem
from pipelex.tools.misc.json_utils import clean_json_dumps


class CliOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


# The active **error** format for the current agent-CLI invocation. JSON is the
# default so any error raised before a command opts into markdown (the app
# callback, unknown-command handling, init failures inside the factory) stays
# machine-parseable. The app callback starts it from the program's own
# ``--error-format``; a command with a ``--format`` / ``--error-format`` option
# settles it at its start (use_agent_cli_error_format), and agent_error() follows it.
# The success path is NOT routed through this var — it threads ``output_format``
# explicitly to agent_success_formatted().
_agent_cli_error_format: ContextVar[CliOutputFormat] = ContextVar("agent_cli_error_format", default=CliOutputFormat.JSON)
# The ``--error-format`` given to the program itself, before the command (``pipelex-agent --error-format json validate
# bundle …``), which a command's own ``--format`` does not override.
_agent_cli_root_error_format: ContextVar[CliOutputFormat | None] = ContextVar("agent_cli_root_error_format", default=None)


def set_agent_cli_error_format(error_format: CliOutputFormat) -> None:
    """Set the active error reporting format for the current agent-CLI invocation."""
    _agent_cli_error_format.set(error_format)


def get_agent_cli_error_format() -> CliOutputFormat:
    """Return the active error reporting format (``JSON`` until a command opts in)."""
    return _agent_cli_error_format.get()


def start_agent_cli_error_format(*, root_error_format: CliOutputFormat | None = None) -> None:
    """Start an invocation's error format: the program's own ``--error-format``, else JSON.

    Called by the app callback, the one choke point every command passes through, so a format a command chose cannot
    leak into a later command of the same process.
    """
    _agent_cli_root_error_format.set(root_error_format)
    _agent_cli_error_format.set(root_error_format or CliOutputFormat.JSON)


def use_agent_cli_error_format(*, error_format: CliOutputFormat | None, output_format: CliOutputFormat | None = None) -> None:
    """Settle a command's error format: its own ``--error-format``, else the program's, else its ``--format``, else JSON.

    An ``--error-format`` given anywhere wins over the format the error stream inherits from ``--format``, so a caller
    that forwards ``--error-format`` before the command (as ``mthds-agent`` does) gets it whatever the command's default.
    """
    resolved = error_format or _agent_cli_root_error_format.get() or output_format or CliOutputFormat.JSON
    _agent_cli_error_format.set(resolved)


# -------------------------------------------------------------------------------------------------
# The problem of a failure
# -------------------------------------------------------------------------------------------------


def agent_problem(
    *,
    cause: BaseException | None = None,
    code: ErrorCode | None = None,
    params: Mapping[str, Any] | None = None,
    location: ProblemLocation | None = None,
) -> PipelexProblem:
    """The problem a command reports, in the operator's view.

    A command that refuses something itself, an argument or a file it cannot read, names the code and its parameters,
    and the error it caught, if any, gives the diagnostics. Otherwise the problem is the Pipelex error's own, which its
    code decides; and an error that is no Pipelex error is the registry's catch-all, ``runtime.unexpected``.

    Args:
        cause: The error the command caught, when it caught one.
        code: The code of a refusal the command decides itself.
        params: The parameters of that code.
        location: Where the refusal is, when the command knows.

    Returns:
        The problem, in the operator's view.
    """
    if code is not None:
        return make_problem(code=code, view=ProblemView.OPERATOR, params=params, location=location, diagnostics=failure_diagnostics(cause=cause))
    if cause is None:
        return make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR)
    return failure_problem(error=cause)


def _advice_of(*, error: BaseException | None) -> str | None:
    """The advice nearest ``error`` along its cause chain, which a local CLI prints as a tip, ``None`` when none is given."""
    if not isinstance(error, PipelexError):
        return None
    advice = error.advised_action()
    return advice.detail if advice is not None else None


def _problem_validation_items(*, error: BaseException | None, problem: PipelexProblem) -> list[ValidationErrorItem]:
    """The items of the invalid verdict the problem's errors are, to render as ``validate``'s prose; empty otherwise.

    The Markdown and the JSON report the one problem. The first invalid verdict along ``error``'s cause chain renders
    its items in place of the problem's errors only when it gave every one of them, item for item, so the prose lists
    the faults the JSON's ``errors`` list. Any other problem, one whose errors a wrapper added to or another error gave,
    renders its errors as they are. The walk stops at the first exception that is not a Pipelex error, as every walk
    reading a failure's chain does.
    """
    if error is None or not problem.errors:
        return []
    for node in iter_pipelex_cause_chain(error):
        if isinstance(node, ValidateBundleError):
            verdict_items = node.problem_items() or []
            verdict_faults = [(item.code, item.detail) for item in verdict_items]
            if verdict_faults != [(item.code, item.detail) for item in problem.errors]:
                return []
            return node.validation_error_items()
    return []


def problem_payload(*, problem: PipelexProblem, message: str | None, extras: Mapping[str, Any]) -> dict[str, Any]:
    """The JSON form of a reported problem: its members as written on the wire, then the command's own.

    The command's sentence rides as ``message`` and its facts as further members; none of them replaces a member of the
    problem itself.
    """
    payload = problem.to_wire()
    own_members: dict[str, Any] = {"message": message} if message else {}
    own_members.update(extras)
    for name, value in own_members.items():
        if value is not None and name not in payload:
            payload[name] = value
    return payload


# -------------------------------------------------------------------------------------------------
# The Markdown rendering
# -------------------------------------------------------------------------------------------------

# Members of a reported problem's own the Markdown leaves out of its Details: the verdict an agent reads off the heading.
_MARKDOWN_SILENT_EXTRAS: frozenset[str] = frozenset({"is_valid"})


def _problem_item_lines(*, item: ProblemItem) -> list[str]:
    """One item of a problem as a Markdown list entry, with its suggested fix under it."""
    where = format_problem_location(location=item.location)
    lines = [f"- `{item.code}`: {item.detail}{f' ({where})' if where else ''}"]
    fix = item.suggested_fix
    if fix is not None:
        lines.append(f"  - Suggested fix ({fix.safety}, {fix.fix_code}): {fix.description}")
    return lines


def _fact_lines(*, problem: PipelexProblem) -> list[str]:
    """The facts a rendering states after the problem's sentences: its code and verdict, the request, the run, the place."""
    lines = [f"- Code: `{problem.code}` ({format_problem_verdict(problem=problem)})"]
    if problem.request_id:
        lines.append(f"- Request id: `{problem.request_id}`")
    if problem.pipeline_run_id:
        lines.append(f"- Run: `{problem.pipeline_run_id}`")
    where = format_problem_location(location=problem.location)
    if where:
        lines.append(f"- Location: {where}")
    return lines


def _migration_lines(*, migration: MigrationErrorBlock) -> list[str]:
    """A pending configuration migration: the command that applies it, whether it would write, and its plans."""
    lines = [
        "",
        "### Configuration migration",
        "",
        f"- Remedy: `{migration.remedy}`",
        f"- Would write: {'yes' if migration.would_write else 'no'}",
        f"- Needs attention: {'yes' if migration.needs_attention else 'no'}",
    ]
    if migration.plans:
        plans = [plan.model_dump(mode="json") for plan in migration.plans]
        lines += ["", "```json", clean_json_dumps(plans, indent=2), "```"]
    return lines


def _diagnostics_lines(*, diagnostics: ProblemDiagnostics | None) -> list[str]:
    """What the operator's diagnostics add for an agent: the error's class, the model and provider, and a migration."""
    if diagnostics is None:
        return []
    lines = ["", "### Diagnostics", "", f"- Error class: `{diagnostics.error_class}`"]
    if diagnostics.model:
        lines.append(f"- Model: `{diagnostics.model}`")
    provider = diagnostics.provider
    if provider is not None and provider.name:
        said = [f"status {provider.status}"] if provider.status is not None else []
        if provider.code:
            said.append(f"code `{provider.code}`")
        lines.append(f"- Provider: `{provider.name}`" + (f" ({', '.join(said)})" if said else ""))
    if diagnostics.migration is not None:
        lines += _migration_lines(migration=diagnostics.migration)
    return lines


def _extras_lines(*, extras: Mapping[str, Any]) -> list[str]:
    """The command's own members, under Details: a scalar on its line, anything else as a JSON block."""
    shown = {name: value for name, value in extras.items() if value is not None and name not in _MARKDOWN_SILENT_EXTRAS}
    if not shown:
        return []
    lines = ["", "### Details", ""]
    for name, value in shown.items():
        if isinstance(value, (str, int, float, bool)):
            lines.append(f"- **{name}:** {value}")
        else:
            lines += [f"- **{name}:**", "", "```json", clean_json_dumps(value, indent=2), "```", ""]
    return lines


def render_problem_markdown(
    *,
    problem: PipelexProblem,
    message: str | None = None,
    extras: Mapping[str, Any] | None = None,
    validation_items: list[ValidationErrorItem] | None = None,
    tip: str | None = None,
) -> str:
    """A reported problem as Markdown, for an agent: the error stream of ``pipelex-agent`` by default.

    The title, the detail, the command's own sentence when it says more, the next step and the tip a local CLI prints
    when the error advises one, then the code with its domain and retry verdict, the request, the run and the location.
    The faults follow: the validation items of an invalid verdict as the grouped prose ``validate`` prints, so an agent
    reads a refused run's items the way it reads an invalid verdict's, and any other problem's items one per line. Then
    the diagnostics and the command's own members.

    Args:
        problem: The problem, in the operator's view.
        message: The command's own sentence.
        extras: The command's own members.
        validation_items: The items of the invalid verdict the problem's errors are, rendered in their place as prose.
        tip: The advice nearest the error along its cause chain (:meth:`PipelexError.advised_action`), which a local CLI
            prints and no problem carries.

    Returns:
        The Markdown, with no trailing newline.
    """
    lines: list[str] = [f"## {problem.title}", "", problem.detail]
    if message and message != problem.detail:
        lines += ["", message]
    lines += ["", f"**Next step** (`{problem.next_step.kind}`): {problem.next_step.detail}"]
    if tip and tip != problem.next_step.detail:
        lines += ["", f"💡 {tip}"]
    lines.append("")
    lines += _fact_lines(problem=problem)
    if validation_items:
        lines += ["", format_validation_error_items_markdown(validation_items)]
    elif problem.errors:
        lines += ["", "### Errors", ""]
        for item in problem.errors:
            lines += _problem_item_lines(item=item)
    lines += _diagnostics_lines(diagnostics=problem.diagnostics)
    lines += _extras_lines(extras=extras or {})
    return "\n".join(lines)


# -------------------------------------------------------------------------------------------------
# Reporting a failure
# -------------------------------------------------------------------------------------------------


def _emit_problem(
    *,
    problem: PipelexProblem,
    message: str | None,
    extras: Mapping[str, Any],
    validation_items: list[ValidationErrorItem],
    markdown_footer: str | None = None,
    markdown_extras: Mapping[str, Any] | None = None,
    tip: str | None = None,
) -> None:
    """Print the problem on stderr in the active error format, and note its code for the command's usage statistics.

    The Markdown lists ``markdown_extras`` under its Details when they are given, in place of ``extras``, for a command
    whose own members the footer already says in prose, and prints ``tip``, which the JSON problem never carries.
    """
    # The command's usage statistics carry the same classification, never the error itself.
    note_command_error(error=usage_stats_error_of_problem(problem=problem))
    match get_agent_cli_error_format():
        case CliOutputFormat.JSON:
            print(clean_json_dumps(problem_payload(problem=problem, message=message, extras=extras), indent=2), file=sys.stderr)
        case CliOutputFormat.MARKDOWN:
            shown_extras = extras if markdown_extras is None else markdown_extras
            markdown = render_problem_markdown(problem=problem, message=message, extras=shown_extras, validation_items=validation_items, tip=tip)
            if markdown_footer:
                markdown = f"{markdown}\n\n{markdown_footer}"
            print(markdown, file=sys.stderr)


def agent_error(
    message: str,
    *,
    cause: BaseException | None = None,
    code: ErrorCode | None = None,
    params: Mapping[str, Any] | None = None,
    location: ProblemLocation | None = None,
    exit_code: int = 1,
    fallback_tip: str | None = None,
    **extra: Any,
) -> NoReturn:
    """Report a failure as its problem on stderr, in the active error format, and exit with ``exit_code`` (default 1).

    Dispatches on the active error format (see :func:`use_agent_cli_error_format`): JSON by default, Markdown when the
    invocation asked for it with ``--format`` or ``--error-format``, so every call site follows it for free, including
    sites in factory or unknown-command code that never see a Typer option. The problem is
    :func:`agent_problem`'s: the code the command names for a refusal of its own, else the caught Pipelex error's own,
    else ``runtime.unexpected``.

    Args:
        message: The command's own sentence, which rides beside the problem as ``message``.
        cause: The error the command caught; chained with ``raise ... from``.
        code: The code of a refusal the command decides itself, such as ``client.argument_invalid``.
        params: The parameters of that code.
        location: Where the refusal is, when the command knows.
        exit_code: Process exit code. 1 (default) marks a produced negative
            verdict; the validate commands pass 2 for no-verdict conditions
            (bad args, unresolvable target, setup error) per the 0/1/2 policy.
        fallback_tip: The advice the Markdown prints when ``cause``'s chain gives none, such as the recovery path of a
            boot that failed; like any tip, the JSON problem never carries it.
        **extra: The command's own members, beside the problem's; none replaces a member of the problem.
    """
    problem = agent_problem(cause=cause, code=code, params=params, location=location)
    _emit_problem(
        problem=problem,
        message=message,
        extras=extra,
        validation_items=_problem_validation_items(error=cause, problem=problem),
        tip=_advice_of(error=cause) or fallback_tip,
    )
    raise typer.Exit(exit_code) from cause


def agent_argument_error(
    message: str, *, argument: str, reason: str, cause: BaseException | None = None, exit_code: int = 1, **extra: Any
) -> NoReturn:
    """Refuse an argument of the command, before anything ran: ``client.argument_invalid``, naming the argument and why.

    Args:
        message: The command's own sentence.
        argument: The argument refused, as the command line gave it or as its option names it.
        reason: Why it was refused, in a few words.
        cause: The error the refusal was raised from, when there is one.
        exit_code: Process exit code.
        **extra: The command's own members.
    """
    agent_error(
        message, cause=cause, code=CoreCode.CLIENT_ARGUMENT_INVALID, params={"argument": argument, "reason": reason}, exit_code=exit_code, **extra
    )


def agent_file_error(
    message: str, *, path: str | Path, reason: str, cause: BaseException | None = None, exit_code: int = 1, **extra: Any
) -> NoReturn:
    """Refuse a local file the command cannot read: ``client.file_unreadable``, naming the file and why.

    Args:
        message: The command's own sentence.
        path: The file, as the command was given it.
        reason: Why it cannot be read, in a few words, such as ``not found``.
        cause: The error the refusal was raised from, when there is one.
        exit_code: Process exit code.
        **extra: The command's own members.
    """
    agent_error(
        message, cause=cause, code=CoreCode.CLIENT_FILE_UNREADABLE, params={"path": str(path), "reason": reason}, exit_code=exit_code, **extra
    )


def agent_unreadable_file_error(*, error: OSError, path: str | Path, exit_code: int = 1) -> NoReturn:
    """Refuse a local file the operating system would not let the command read: ``client.file_unreadable``.

    The file named is the one the error names, else ``path``, the file the command was handed; the reason is the
    system's own (:func:`file_read_failure_reason`).

    Args:
        error: The error reading the file raised.
        path: The file the command was handed.
        exit_code: Process exit code.
    """
    unreadable = os.fsdecode(error.filename) if isinstance(error.filename, (str, bytes)) else str(path)
    reason = file_read_failure_reason(error=error)
    agent_file_error(f"Cannot read '{unreadable}': {reason}", path=unreadable, reason=reason, cause=error, exit_code=exit_code)


def file_read_failure_reason(*, error: OSError | UnicodeDecodeError) -> str:
    """Why a local file could not be read, in the few words ``client.file_unreadable`` names: the system's own reason."""
    if isinstance(error, UnicodeDecodeError):
        return "not UTF-8 text"
    return error.strerror.lower() if error.strerror else "cannot be opened"


def agent_success(result: dict[str, Any]) -> None:
    """Print a structured JSON success result to stdout.

    Args:
        result: Dictionary to serialize as JSON.
    """
    print(clean_json_dumps(result, indent=2))


def agent_success_formatted(
    result: dict[str, Any],
    *,
    markdown_renderer: Callable[[dict[str, Any]], str],
    output_format: CliOutputFormat,
) -> None:
    """Emit a success result in the given CLI output format.

    JSON format serializes ``result`` to stdout; markdown format prints the
    output of ``markdown_renderer(result)`` to stdout.

    The format is passed explicitly (not read from a ContextVar) because every
    call site lives inside a command function that already has its ``--format``
    parameter in scope. Only the error path needs the ContextVar — see
    :func:`agent_error`.

    Args:
        result: The structured result dict (the JSON-mode payload).
        markdown_renderer: Renders ``result`` into a markdown string.
        output_format: The success output format for this command invocation.
    """
    match output_format:
        case CliOutputFormat.JSON:
            agent_success(result)
        case CliOutputFormat.MARKDOWN:
            print(markdown_renderer(result))


def _validate_fix_footer(
    *,
    items: list[ValidationErrorItem],
    bundle_path: Path,
    library_dirs: list[Path] | None,
    allow_signatures: bool,
) -> str:
    """The footer of the ``validate`` failure Markdown: the exact fix command when items carry a fix, else a pointer to them.

    Mirrors the human ``handle_validate_bundle_error`` panel: the same predicate and the same command shape, with
    ``pipelex-agent`` as the program. Doc and Discord links are left out, being noise for an LLM fixing a ``.mthds`` file.
    """
    fixable_count = count_applicable_fixes(items, bundle_path=bundle_path, library_dirs=library_dirs)
    if fixable_count:
        fix_command = build_fix_command(
            executable="pipelex-agent", bundle_path=bundle_path, library_dirs=library_dirs, allow_signatures=allow_signatures
        )
        return f"💡 {fixable_count} of these errors can be fixed automatically — run: `{fix_command}`"
    return "💡 These errors have no automatic fix — review the messages above and edit the bundle."


def agent_error_validate_bundle(
    exc: ValidateBundleError,
    *,
    bundle_path: Path,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = False,
) -> NoReturn:
    """Report the ``validate`` invalid verdict as its problem on stderr, format-aware, and exit 1.

    The verdict's problem (``method.invalid``, its faults in ``errors``) carries ``is_valid: false`` and the
    ``bundle_path`` beside its members, which a software consumer (a hook pins ``--error-format json``) branches on.
    Its Markdown renders the faults as the grouped prose ``validate`` prints, with each suggested fix, and ends with a
    fix-aware footer naming the exact ``pipelex-agent fix bundle`` command when items carry a fix.

    Args:
        exc: The bundle-validation failure to report.
        bundle_path: The bundle file / pipeline directory that failed validation.
        library_dirs: The ``-L/--library-dir`` values, echoed into the markdown fix-command footer.
        allow_signatures: Whether the invocation accepted ``PipeSignature`` placeholders; echoed into
            the markdown fix-command footer so the suggested fix keeps the same leniency.
    """
    items = exc.validation_error_items()
    _emit_problem(
        problem=exc.to_problem(view=ProblemView.OPERATOR),
        message=exc.message,
        extras={"is_valid": False, "bundle_path": str(bundle_path)},
        validation_items=items,
        # The fix-aware footer stands in for the verdict's class-level advice, which would only repeat it less precisely.
        markdown_footer=_validate_fix_footer(items=items, bundle_path=bundle_path, library_dirs=library_dirs, allow_signatures=allow_signatures),
    )
    raise typer.Exit(1) from exc


def agent_error_fix_bundle(*, result: FixBundleResult, bundle_path: str, message: str) -> NoReturn:
    """Report a ``fix bundle`` that left the bundle invalid as its problem on stderr, format-aware, and exit 1.

    The problem is the method's that does not validate, ``method.invalid``, its faults the remaining errors. Beside its
    members ride ``bundle_path`` and the fix result's own fields (``is_valid``, ``iterations``, ``fixes_applied``,
    ``files_written``, ``bail_reason`` and the rest), the remaining errors being the problem's ``errors``. Its Markdown
    renders the remaining errors as prose, then what the loop applied, why it stopped and what to do next.

    Args:
        result: The fix loop's result, whose verdict is invalid.
        bundle_path: The bundle file the fix started from, resolved.
        message: The command's own sentence.
    """
    # Each remaining error keeps the code `validate` gives it, which the verdict the loop last read decided.
    items = [
        problem_item_of(item=item, code=item_code.code, params=item_code.params)
        for item, item_code in zip(result.remaining_errors, result.remaining_error_codes, strict=True)
    ]
    problem = make_problem(code=CoreCode.METHOD_INVALID, view=ProblemView.OPERATOR, errors=items or None)
    extras: dict[str, Any] = {
        "bundle_path": bundle_path,
        **result.model_dump(mode="json", exclude_none=True, exclude={"remaining_errors", "remaining_error_codes"}),
    }
    _emit_problem(
        problem=problem,
        message=message,
        extras=extras,
        validation_items=result.remaining_errors,
        markdown_footer=format_fix_progress_markdown(result, bundle_path=bundle_path),
        markdown_extras={"bundle_path": bundle_path},
    )
    raise typer.Exit(1)


# -------------------------------------------------------------------------------------------------
# A hosted run's failure: the envelope it had before the problem
# -------------------------------------------------------------------------------------------------

# Statuses that say the request was refused before anything ran, so the same request can succeed later
# (RFC 6585): the envelope marks them retryable unless the answer said otherwise. A 503 is not one of
# them: the hosted plane can answer it after the run completed (see its next step in pipelex.hosted.error_rendering).
_API_RETRYABLE_STATUSES: frozenset[int] = frozenset({429})


def _build_error_source(exc: BaseException) -> list[str]:
    """Build a compact source trace from an exception's cause chain.

    Each entry shows where the exception was raised:
    ``"ExceptionType @ module:line (in function)"``.

    Args:
        exc: The exception (walks ``__cause__`` chain).

    Returns:
        List of source location strings, outermost first.
    """
    sources: list[str] = []
    for current in iter_cause_chain(exc):
        if current.__traceback__ is None:
            sources.append(f"{type(current).__name__} (no traceback)")
            continue
        tbe = traceback.extract_tb(current.__traceback__)
        if tbe:
            frame = tbe[-1]  # default fallback
            for candidate in reversed(tbe):
                if "/pipelex/" in candidate.filename and "/.venv/" not in candidate.filename:
                    frame = candidate
                    break
            location = f"{type(current).__name__} @ {frame.filename}:{frame.lineno} (in {frame.name})"
            sources.append(location)
        else:
            sources.append(f"{type(current).__name__} (no traceback)")
    return sources


# Payload keys that the markdown renderer treats specially (heading / body /
# tip) or omits entirely rather than listing under the "Details" section.
# ``error_source`` is dropped from markdown — it's internal stack frames that
# don't help an LLM fix a `.mthds` file. The field stays in the JSON envelope
# for programmatic consumers.
_MARKDOWN_RESERVED_KEYS: frozenset[str] = frozenset({"error", "error_type", "message", "hint", "error_source", "validation_errors"})


def _typed_validation_items(*, validation_errors: Any) -> list[ValidationErrorItem] | None:
    """The payload's ``validation_errors`` as typed items, or ``None`` when there are none to render as prose.

    ``None`` also when an item does not fit this pipelex's ``ValidationErrorItem``: an API runner's
    items come off the wire, and one from a newer runner can carry an ``error_type`` or a field this
    version does not know. The caller then keeps the items as JSON under Details rather than losing them.
    """
    if not isinstance(validation_errors, list) or not validation_errors:
        return None
    try:
        return [ValidationErrorItem.model_validate(item) for item in cast("list[dict[str, Any]]", validation_errors)]
    except ValidationError:
        return None


def _render_error_markdown(payload: dict[str, Any]) -> str:
    """Render a hosted run's error envelope as agent-readable markdown.

    ``validation_errors`` render as the same grouped prose ``validate`` prints, rather than as a JSON
    dump under Details, so an agent reads a refused run's items the way it reads an invalid verdict's.
    Items this version cannot type stay under Details as JSON.
    """
    lines: list[str] = [f"# Error: {payload['error_type']}", "", str(payload["message"])]

    hint = payload.get("hint")
    if hint:
        lines += ["", f"> 💡 **Hint:** {hint}"]

    reserved_keys = _MARKDOWN_RESERVED_KEYS
    validation_errors = payload.get("validation_errors")
    items = _typed_validation_items(validation_errors=validation_errors)
    if items:
        lines += ["", format_validation_error_items_markdown(items)]
    elif validation_errors:
        reserved_keys = _MARKDOWN_RESERVED_KEYS - {"validation_errors"}

    detail_keys = [key for key in payload if key not in reserved_keys]
    if detail_keys:
        lines += ["", "## Details", ""]
        for key in detail_keys:
            value = payload[key]
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"- **{key}:** {value}")
            else:
                lines += [f"- **{key}:**", "", "```json", clean_json_dumps(value, indent=2), "```", ""]

    return "\n".join(lines)


def _print_hosted_envelope(*, payload: dict[str, Any]) -> None:
    """Print a hosted run's error envelope on stderr in the active error format."""
    match get_agent_cli_error_format():
        case CliOutputFormat.JSON:
            print(clean_json_dumps(payload, indent=2), file=sys.stderr)
        case CliOutputFormat.MARKDOWN:
            print(_render_error_markdown(payload), file=sys.stderr)


def agent_error_hosted_envelope(message: str, *, error_type: str, cause: BaseException, exit_code: int = 1, **extra: Any) -> NoReturn:
    """Report a hosted run's failure in the envelope a hosted run had before the problem, and exit with ``exit_code``.

    ``error: true``, ``error_type`` and ``message``, then the ``hint``: the advice nearest the error along its chain, else
    its code's next step, ``runtime.unexpected``'s for an error that is no Pipelex error. For a Pipelex error, the
    ``error_code``, ``error_domain`` and ``retryable`` (only when true) its code decides; then the client-side
    ``error_source``, and the fields read off the hosted plane's answer in ``extra``, which win.

    Args:
        message: The failure's sentence.
        error_type: The class the hosted answer names, else the error's own.
        cause: The error the hosted run raised.
        exit_code: Process exit code.
        **extra: The fields read off the hosted plane's answer.
    """
    problem = agent_problem(cause=cause)
    payload: dict[str, Any] = {
        "error": True,
        "error_type": error_type,
        "message": message,
        "hint": _advice_of(error=cause) or problem.next_step.detail,
    }
    if isinstance(cause, PipelexError):
        if problem.is_retryable:
            payload["retryable"] = True
        payload["error_domain"] = ErrorDomain.from_problem_domain(problem.effective_domain)
        payload["error_code"] = problem.code
    payload["error_source"] = _build_error_source(cause)
    payload.update(extra)
    note_command_error(error=usage_stats_error(error=cause))
    _print_hosted_envelope(payload=payload)
    raise typer.Exit(exit_code) from cause


def _non_empty_string(*, value: Any) -> str | None:
    """A problem member that is a non-empty string, else ``None``."""
    return value if isinstance(value, str) and value else None


def _string_list(*, value: Any) -> list[str] | None:
    """A problem member that is a non-empty list of strings, else ``None``."""
    if not isinstance(value, list) or not value:
        return None
    entries = cast("list[Any]", value)
    if not all(isinstance(entry, str) for entry in entries):
        return None
    return cast("list[str]", entries)


def api_response_error_payload(*, error: ApiResponseError) -> dict[str, Any]:
    """The error envelope of a request the hosted API answered non-2xx, read off the problem document it sent.

    - ``error_type`` is the runner's error class when the problem names one: ``ValidateBundleError`` for a bundle
      refused at load, and the root fault (``ModelNotFoundError``, ``StuffFactoryError``) for a run that failed.
      ``ApiResponseError`` when the answer names no class, as a gateway's error page does not.
    - ``message`` is ``API POST /v1/start failed (422): <reason>``, the error's own message without the next step
      it appends, which ``hint`` carries. On a failed run the runner's reason is located at the failing pipe and its
      path, ``Pipe 'condense_article' failed (digest_article → condense_article): …``.
    - ``hint`` is the runner's next step, ``user_action.detail``. An answer that advised none, such as the ones the
      hosted plane authors in front of the runner (a refused key, a rate limit, a runner it cannot reach), gets the
      next step of its status from ``pipelex.hosted.error_rendering``, the table the human CLI reads too, else one by
      status class (a 4xx asks for a change to the request, anything else for a report).
    - ``retryable`` (only when true, as on every envelope), ``error_domain`` and ``error_category`` are the answer's,
      with no local fallback, since only the runner knows whether the caller or its operator has to act; the verdict
      pipelex-sdk decides for every refusal is not read, since it fills an unsent member from its own table. The one
      exception is ``retryable`` on a 429 that did not say, a refusal sent before anything ran. A 503 is never
      inferred retryable: a hosted plane can answer it after the run completed.
    - ``validation_errors`` are the runner's items, each whole, as it sent them.
    - ``pipe_code`` and ``pipe_stack`` when the problem carries them as members.
    - ``error_code`` is the problem's ``code`` member, the stable code a hosted plane gives its own refusals
      (``rate_limited``, ``unauthorized``), and ``retry_after_seconds`` the ``Retry-After`` header's delay.
    - ``http_status`` and ``request_id`` are what to quote when the fault is the runner's.
    - ``error_source`` is the client-side trace, as on every JSON envelope.
    """
    problem: dict[str, Any] = error.problem_document or {}
    payload: dict[str, Any] = {
        "error": True,
        "error_type": error.error_type or type(error).__name__,
        "message": hosted_refusal_message(error=error),
        "hint": hosted_refusal_next_step(error=error),
    }
    sent = sent_verdict(error=error)
    if sent.retryable or (sent.retryable is None and error.status in _API_RETRYABLE_STATUSES):
        payload["retryable"] = True
    if sent.error_domain:
        payload["error_domain"] = sent.error_domain
    if error_category := _non_empty_string(value=problem.get("error_category")):
        payload["error_category"] = error_category
    if error.validation_errors:
        payload["validation_errors"] = [item.model_dump(mode="json") for item in error.validation_errors]
    if pipe_code := _non_empty_string(value=problem.get("pipe_code")):
        payload["pipe_code"] = pipe_code
    if pipe_stack := _string_list(value=problem.get("pipe_stack")):
        payload["pipe_stack"] = pipe_stack
    if error_code := _non_empty_string(value=problem.get("code")):
        payload["error_code"] = error_code
    retry_after = error.headers.get("retry-after", "").strip()
    if retry_after.isdigit():
        payload["retry_after_seconds"] = int(retry_after)
    payload["http_status"] = error.status
    if error.request_id:
        payload["request_id"] = error.request_id
    payload["error_source"] = _build_error_source(error)
    return payload


def agent_error_api_response(*, error: ApiResponseError) -> NoReturn:
    """Emit the envelope of a request the hosted API refused to stderr, format-aware, and exit 1.

    The sibling of :func:`agent_error_hosted_envelope` for the one error a hosted refusal arrives as, its envelope
    read off the hosted API's answer (see :func:`api_response_error_payload`).

    Args:
        error: The refusal pipelex-sdk's ``PipelexAPIClient`` raised.
    """
    payload = api_response_error_payload(error=error)
    # The statistics say what the envelope says: what the hosted API sent, never what the SDK inferred from the status.
    if (sent_error := sent_usage_stats_error(error=error)) is not None:
        note_command_error(error=sent_error)
    _print_hosted_envelope(payload=payload)
    raise typer.Exit(1) from error
