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

A run on a runner (``--runner hosted``) reports the problem the runner or the client produced, in the caller's view,
through :func:`agent_error_problem`: the problem was built elsewhere, so this module prints it as it came.
"""

import os
import sys
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn

import typer
from mthds.protocol.problem.models import FixSafety, ProblemItem, ProblemLocation
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError, ValidationErrorItem
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.failure_problem import failure_diagnostics, failure_problem, format_problem_location, format_problem_verdict
from pipelex.errors.problem import (
    MigrationErrorBlock,
    PipelexProblem,
    ProblemDiagnostics,
    ProblemView,
    make_problem,
)
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes.fix_loop import FixBundleResult
from pipelex.pipeline.fixes.fix_render import format_fix_progress_markdown
from pipelex.pipeline.validation_errors import problem_item_of
from pipelex.pipeline.validation_render import build_fix_command, count_applicable_fixes
from pipelex.system.usage_stats.usage_stats_client import note_command_error
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsError
from pipelex.system.usage_stats.usage_stats_runs import usage_stats_error_of_problem
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
    """One item of a problem as a Markdown list entry: its code, its sentence and where, then its suggestions and its fix.

    An unsafe fix, or one of a safety this reader does not know, says it needs confirming before it is applied.
    """
    where = format_problem_location(location=item.location)
    lines = [f"- `{item.code}`: {item.detail}{f' ({where})' if where else ''}"]
    if item.suggestions:
        lines.append(f"  - Suggestions: {', '.join(f'`{suggestion}`' for suggestion in item.suggestions)}")
    fix = item.suggested_fix
    if fix is not None:
        safety: str
        match fix.effective_safety:
            case FixSafety.SAFE:
                safety = "safe"
            case FixSafety.UNSAFE:
                safety = "unsafe, confirm before applying"
        lines.append(f"  - Suggested fix (`{fix.fix_code}`, {safety}): {fix.description}")
    return lines


def _errors_lines(*, problem: PipelexProblem, heading: str) -> list[str]:
    """A problem's faults, one item per line under ``heading``; nothing when it lists none."""
    if not problem.errors:
        return []
    lines = ["", heading, ""]
    for item in problem.errors:
        lines += _problem_item_lines(item=item)
    return lines


def _problem_head_lines(*, problem: PipelexProblem, depth: int, message: str | None = None, tip: str | None = None) -> list[str]:
    """A problem under a heading of ``depth``: its title, its detail, the next step, its facts and its faults.

    The command's own sentence and the tip are added when they say more than the detail and the next step. Its faults
    are listed one heading level down. The reported problem and the run's own problem it nests both render through
    here, at their own depths.
    """
    heading = "#" * depth
    lines: list[str] = [f"{heading} {problem.title}", "", problem.detail]
    if message and message != problem.detail:
        lines += ["", message]
    lines += ["", f"**Next step** (`{problem.next_step.kind}`): {problem.next_step.detail}"]
    if tip and tip != problem.next_step.detail:
        lines += ["", f"💡 {tip}"]
    lines.append("")
    lines += _fact_lines(problem=problem)
    lines += _errors_lines(problem=problem, heading=f"{heading}# Errors")
    return lines


def _run_error_lines(*, run_error: PipelexProblem | None) -> list[str]:
    """The failed run's own problem, nested in the problem of a read of its results: what made the run fail, and where."""
    if run_error is None:
        return []
    return ["", "### The run's own problem", "", *_problem_head_lines(problem=run_error, depth=4)]


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
    tip: str | None = None,
) -> str:
    """A reported problem as Markdown, for an agent: the error stream of ``pipelex-agent`` by default.

    The title, the detail, the command's own sentence when it says more, the next step and the tip a local CLI prints
    when the error advises one, then the code with its domain and retry verdict, the request, the run and the location.
    The faults follow, the problem's ``errors`` one per line with their code, sentence, location, suggestions and
    suggested fix, the same items the JSON lists, whether a local verdict or a runner gave them. Then the failed run's
    own problem when a read of its results nests one, the diagnostics and the command's own members.

    Args:
        problem: The problem, in the view its reader is given.
        message: The command's own sentence.
        extras: The command's own members.
        tip: The advice nearest the error along its cause chain (:meth:`PipelexError.advised_action`), which a local CLI
            prints and no problem carries.

    Returns:
        The Markdown, with no trailing newline.
    """
    lines = _problem_head_lines(problem=problem, depth=2, message=message, tip=tip)
    lines += _run_error_lines(run_error=problem.run_error)
    lines += _diagnostics_lines(diagnostics=problem.diagnostics)
    lines += _extras_lines(extras=extras or {})
    return "\n".join(lines)


# -------------------------------------------------------------------------------------------------
# Reporting a failure
# -------------------------------------------------------------------------------------------------


def _print_problem(
    *,
    problem: PipelexProblem,
    message: str | None,
    extras: Mapping[str, Any],
    markdown_footer: str | None = None,
    markdown_extras: Mapping[str, Any] | None = None,
    tip: str | None = None,
) -> None:
    """Print the problem on stderr in the active error format.

    The Markdown lists ``markdown_extras`` under its Details when they are given, in place of ``extras``, for a command
    whose own members the footer already says in prose, and prints ``tip``, which the JSON problem never carries.
    """
    match get_agent_cli_error_format():
        case CliOutputFormat.JSON:
            print(clean_json_dumps(problem_payload(problem=problem, message=message, extras=extras), indent=2), file=sys.stderr)
        case CliOutputFormat.MARKDOWN:
            shown_extras = extras if markdown_extras is None else markdown_extras
            markdown = render_problem_markdown(problem=problem, message=message, extras=shown_extras, tip=tip)
            if markdown_footer:
                markdown = f"{markdown}\n\n{markdown_footer}"
            print(markdown, file=sys.stderr)


def _emit_problem(
    *,
    problem: PipelexProblem,
    message: str | None,
    extras: Mapping[str, Any],
    markdown_footer: str | None = None,
    markdown_extras: Mapping[str, Any] | None = None,
    tip: str | None = None,
) -> None:
    """Print the problem on stderr in the active error format, and note its code for the command's usage statistics."""
    # The command's usage statistics carry the same classification, never the error itself.
    note_command_error(error=usage_stats_error_of_problem(problem=problem))
    _print_problem(problem=problem, message=message, extras=extras, markdown_footer=markdown_footer, markdown_extras=markdown_extras, tip=tip)


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
    _emit_problem(problem=problem, message=message, extras=extra, tip=_advice_of(error=cause) or fallback_tip)
    raise typer.Exit(exit_code) from cause


def agent_error_problem(
    *,
    problem: PipelexProblem,
    cause: BaseException,
    noted_error: UsageStatsError | None,
    message: str | None = None,
    exit_code: int = 1,
) -> NoReturn:
    """Report a problem built elsewhere as it came, on stderr in the active error format, and exit with ``exit_code``.

    The failure of a run on a runner is the problem the runner answered or the client decided, in the caller's view, so
    this CLI neither rebuilds nor reclassifies it. The usage statistics note ``noted_error``, which the caller decides:
    a refusal a server answered is noted by what its body sent alone, and not at all when it sent no code. The Markdown
    prints the advice ``cause`` gives, when it is a Pipelex error that gives one, as its tip.

    Args:
        problem: The problem to report.
        cause: The error the problem belongs to; chained with ``raise ... from``.
        noted_error: What the command's usage statistics record, ``None`` to record nothing.
        message: The command's own sentence, when it says what the problem does not.
        exit_code: Process exit code.
    """
    if noted_error is not None:
        note_command_error(error=noted_error)
    _print_problem(problem=problem, message=message, extras={}, tip=_advice_of(error=cause))
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


def agent_unreadable_file_error(*, error: OSError, exit_code: int = 1) -> NoReturn:
    """Refuse a local file the operating system would not let the command read: ``client.file_unreadable``.

    The file named is the one the error names, and the reason is the system's own (:func:`file_read_failure_reason`).
    An error that names no file, such as a refused connection, a timeout or a TLS failure met while the command ran,
    refuses no file: it is reported as the unexpected failure it is, ``runtime.unexpected``, as the command's boundary
    reports any other exception that is no Pipelex error.

    Args:
        error: The error the system raised.
        exit_code: Process exit code.
    """
    if error.filename is None:
        agent_error(str(error), cause=error, exit_code=exit_code)
    unreadable = os.fsdecode(error.filename) if isinstance(error.filename, (str, bytes)) else str(error.filename)
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
    Its Markdown lists the same items, each with its code, sentence, location, suggestions and suggested fix, and ends
    with a fix-aware footer naming the exact ``pipelex-agent fix bundle`` command when items carry a fix.

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
        # The fix-aware footer stands in for the verdict's class-level advice, which would only repeat it less precisely.
        markdown_footer=_validate_fix_footer(items=items, bundle_path=bundle_path, library_dirs=library_dirs, allow_signatures=allow_signatures),
    )
    raise typer.Exit(1) from exc


def agent_error_fix_bundle(*, result: FixBundleResult, bundle_path: str, message: str) -> NoReturn:
    """Report a ``fix bundle`` that left the bundle invalid as its problem on stderr, format-aware, and exit 1.

    The problem is the method's that does not validate, ``method.invalid``, its faults the remaining errors. Beside its
    members ride ``bundle_path`` and the fix result's own fields (``is_valid``, ``iterations``, ``fixes_applied``,
    ``files_written``, ``bail_reason`` and the rest), the remaining errors being the problem's ``errors``. Its Markdown
    lists the remaining errors as the problem's items, then what the loop applied, why it stopped and what to do next.

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
        markdown_footer=format_fix_progress_markdown(result, bundle_path=bundle_path),
        markdown_extras={"bundle_path": bundle_path},
    )
    raise typer.Exit(1)
