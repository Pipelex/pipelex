"""Helpers for structured output in agent CLI commands.

Two independent format axes:

- **Success output** is driven by the per-command ``--format`` Typer option, passed
  explicitly to :func:`agent_success_formatted`. No hidden state — every success
  call site lives inside a command function that has ``output_format`` in scope.
- **Error reporting** is driven by ``--error-format`` (or by ``--format``'s value
  when ``--error-format`` is omitted). Errors must be format-aware from sites far
  from any Typer command (init failures in ``agent_cli_factory.py``,
  ``UnknownCommandError`` from the Typer group, validation errors in the app
  callback, etc.), so the error format is carried in a module-level
  ``ContextVar``. JSON is the default so any error raised before a command opts
  in stays machine-parseable.

Commands that don't accept ``--format`` (``inputs``, ``concept``, ``pipe``,
``fmt``, ``lint``) never touch the ContextVar and
therefore emit JSON errors via the default.
"""

import sys
import traceback
from collections.abc import Callable
from contextvars import ContextVar
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn, cast

import typer
from mthds.runners.api.exceptions import ApiResponseError
from pydantic import ValidationError

from pipelex.base_exceptions import PipelexError, ValidationErrorItem, iter_cause_chain
from pipelex.pipe_run.located_failure import find_root_fault
from pipelex.pipeline.exceptions import PipelineExecutionError, ValidateBundleError
from pipelex.pipeline.validation_render import build_fix_command, count_applicable_fixes, format_validation_error_items_markdown
from pipelex.tools.misc.json_utils import clean_json_dumps

# Module-level capture for setup-time warnings (currently used by RemoteConfigStaleWarning).
# The agent CLI factory writes here when it catches a stale-cache warning during ``Pipelex.make``
# and ``agent_success`` reads back here to attach the ``warnings`` field to the envelope so
# machine consumers see the provenance.
_CAPTURED_WARNINGS: list[dict[str, Any]] = []


def record_setup_warning(warning_payload: dict[str, Any]) -> None:
    """Stash a structured warning for inclusion in the next ``agent_success`` envelope.

    Callers pass a dict shaped like ``{"type": "RemoteConfigStale", "message": "..."}``;
    the contents are surfaced verbatim by ``agent_success``.
    """
    _CAPTURED_WARNINGS.append(warning_payload)


def consume_setup_warnings() -> list[dict[str, Any]]:
    """Drain the captured warnings buffer. Returns whatever was recorded and clears state.

    Called once per envelope so successive commands within a single Python process don't
    re-emit yesterday's warnings.
    """
    drained = list(_CAPTURED_WARNINGS)
    _CAPTURED_WARNINGS.clear()
    return drained


class CliOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


# The active **error** format for the current agent-CLI invocation. JSON is the
# default so any error raised before a command opts into markdown (the app
# callback, unknown-command handling, init failures inside the factory) stays
# machine-parseable. A command with a ``--format`` / ``--error-format`` option
# calls set_agent_cli_error_format() at its start, and agent_error() follows it.
# The success path is NOT routed through this var — it threads ``output_format``
# explicitly to agent_success_formatted().
_agent_cli_error_format: ContextVar[CliOutputFormat] = ContextVar("agent_cli_error_format", default=CliOutputFormat.JSON)


def set_agent_cli_error_format(error_format: CliOutputFormat) -> None:
    """Set the active error reporting format for the current agent-CLI invocation."""
    _agent_cli_error_format.set(error_format)


def get_agent_cli_error_format() -> CliOutputFormat:
    """Return the active error reporting format (``JSON`` until a command opts in)."""
    return _agent_cli_error_format.get()


# Fallback error-classification lookups, keyed by error_type name.
#
# agent_error() reads error_domain / user_action from a PipelexError cause's
# to_error_report() first; these dicts are the fallback for error types that
# cannot self-describe: builtin and third-party exceptions, synthetic error_type
# labels passed straight to agent_error(), and PipelexError subclasses not yet
# migrated to class-level metadata. A PipelexError subclass that declares
# class-level error_domain / user_action must NOT appear here — enforced by
# tests/unit/pipelex/cli/test_agent_output_drift.py.
#
# A CogtError subclass carrying an error_category self-describes too, without any
# class-level error_domain of its own: InferenceErrorCategory.error_domain derives
# one, and to_error_report() puts it on the report, so the report-first read at the
# bottom of agent_error() always wins and an AGENT_ERROR_DOMAINS entry for such a
# class can never be read. Those are barred from this dict as well, by the same
# drift test — a dead entry is exactly the rot it exists to prevent. When the
# derived domain is not the one this CLI wants, fix it on the class (declare an
# explicit error_domain, as ModelChoiceNotFoundError does), never here.
# An unknown model is the author's input fault, whether it is raised bare by the deck check or located
# on its pipe: the next step is to correct the reference, not to diagnose the installation.
_UNKNOWN_MODEL_HINT = (
    "Check model name for typos. Use 'pipelex-agent check-model <name> -t <type>' "
    "to validate or 'pipelex-agent models -t <type>' to list available models."
)

_API_CREDENTIALS_HINT = (
    "Set MTHDS_API_KEY and MTHDS_BASE_URL (the runner's origin), or run 'mthds config set api-key <key>' and 'mthds config set base-url <url>'"
)
_API_RATE_LIMITED_HINT = "Too many requests: wait retry_after_seconds when the error carries it, otherwise a few seconds, then run again"
# A 503 does not say whether the run happened: a hosted plane can answer it before forwarding the
# request and also after the run completed, when it failed to record the result. So it is never
# marked retryable, and its hint warns that running again can repeat a paid run.
_API_UNAVAILABLE_HINT = (
    "The runner or the service in front of it was unavailable. It may have failed before the run or after it, "
    "so running again can repeat a paid run: wait retry_after_seconds when the error carries it, then run again "
    "only if a repeated run is acceptable"
)
# The next step of a 4xx refusal that advised none and whose status has no hint of its own.
API_REFUSAL_CALLER_HINT = (
    "The runner refused the request: change what the message names (the method, the inputs or the configuration), then run again"
)

# The next step of a refusal whose answer advised none, by its HTTP status. These are the answers a
# hosted plane authors itself, in front of the runner, and they carry no `user_action`: the gateway's
# refusal of a key, an unknown route, the platform's rate limiter, a service it cannot reach.
API_REFUSAL_HINTS_BY_STATUS: dict[int, str] = {
    401: f"The runner refused the credentials. {_API_CREDENTIALS_HINT}",
    403: (
        "The runner refused the request: check that MTHDS_API_KEY is a valid key for the runner at MTHDS_BASE_URL; "
        "when it is, the message says what this request may not do"
    ),
    404: "The runner has no such route: check that MTHDS_BASE_URL is the runner's origin, with no path such as /v1",
    429: _API_RATE_LIMITED_HINT,
    503: _API_UNAVAILABLE_HINT,
}

# Statuses that say the request was refused before anything ran, so the same request can succeed later
# (RFC 6585): the envelope marks them retryable unless the answer said otherwise. A 503 is not one of
# them, see _API_UNAVAILABLE_HINT.
_API_RETRYABLE_STATUSES: frozenset[int] = frozenset({429})

AGENT_ERROR_HINTS: dict[str, str] = {
    # Model/routing errors
    "ModelChoiceNotFoundError": _UNKNOWN_MODEL_HINT,
    "PipeOperatorModelChoiceError": _UNKNOWN_MODEL_HINT,
    "PipeOperatorModelAvailabilityError": "Run 'pipelex-agent doctor' to check available models and verify API keys",
    "ModelDeckPresetValidatonError": (
        "Run 'pipelex-agent doctor' to check model configuration. "
        "Update the preset model, configure it in an enabled backend, or enable a supporting backend"
    ),
    # Validation errors
    "PipeValidationError": "Check pipe inputs, outputs, and concept references for consistency",
    "FixBundleError": "Inspect remaining_errors and bail_reason, adjust the bundle, then run fix or validate again",
    # Execution errors
    "PipeExecutionError": "A pipe input validation failed during pipeline execution. Check the error message for the failing model and field.",
    # File/input errors
    "FileNotFoundError": "Verify the file path exists and is accessible from the current working directory",
    "ArgumentError": "Check command usage with 'pipelex-agent <command> --help'",
    "JSONDecodeError": "Verify the JSON input is valid (check for trailing commas, unquoted keys, etc.)",
    "StdinEnvelopeShapeError": (
        "The JSON parsed — its shape is what the envelope contract refuses. In a 'working_memory' envelope each stuff "
        "names its concept as the ref string '<domain>.<Code>'; replace a concept object with its ref, or re-pipe the "
        "output of a current 'pipelex-agent run --with-memory'."
    ),
    # Interpreter errors
    "MthdsParserError": "Check MTHDS file TOML syntax and ensure all referenced concepts and pipes are defined",
    # Configuration/initialization errors
    # Three readings, and two fields on this same payload separate them: an absent `migration`
    # means the file is wrong, and a present one means the migration history has something to say
    # about it — `migration.would_write` then says whether a command repairs it or whether the
    # plans are a diagnosis to act on by hand. Never `pipelex init telemetry` on either of the
    # last two: that writes a fresh file over settings a migration would have kept.
    "TelemetryConfigValidationError": (
        "If this payload carries a 'migration' field, read its 'would_write': true means the "
        "configuration is out of date and 'pipelex-agent migrate --yes' repairs it — run "
        "'pipelex-agent migrate --dry-run --format json' first to show the user what would change. "
        "False means the migration would write nothing and its 'plans' name what to correct by hand. "
        "Without a 'migration' field, correct the telemetry.toml settings named in the message."
    ),
    "BinaryNotFoundError": "Install pipelex-tools: uv tool install pipelex-tools",
    "RemoteConfigUnavailableError": (
        "Run `pipelex init` while online to prime the cache, or disable the Pipelex-managed gateway backends in backends.toml "
        "to operate offline (BYOK)"
    ),
    "RemoteConfigValidationError": (
        "This is a server-side issue; report it on Discord/GitHub. Disable the Pipelex-managed gateway backends in backends.toml as a workaround"
    ),
    "GatewayUnknownModelError": (
        "The deck references a model the gateway doesn't expose. If the source is `cached`, run `pipelex init` while online to refresh; "
        "otherwise update the deck or check the model name."
    ),
    # API runner errors
    "ClientAuthenticationError": _API_CREDENTIALS_HINT,
    "PipelineRequestError": "Check that pipe_code or mthds_contents is provided",
    # The next step of a runner's server-side failure that advised none, when its status has none of its
    # own in API_REFUSAL_HINTS_BY_STATUS (a 4xx gets API_REFUSAL_CALLER_HINT instead). It stands in for
    # the hint keyed on the runner's own class, which names a local command (doctor, check-model) that
    # cannot fix what a remote runner refused.
    "ApiResponseError": (
        "The API runner failed on its side: report it with the request_id, or with the http_status when the error carries no request_id"
    ),
    # Graph errors
    "GraphSpecParseError": "Validate graphspec.json structure; ensure it matches the expected GraphSpec schema",
    # Input/type errors
    "JsonTypeError": "Input file must be a JSON object {...}, not an array or scalar value",
    "TomlError": "Fix the TOML syntax error (the message includes the line and column)",
    "BundleError": "Bundle must declare a 'main_pipe' or use the --pipe flag to specify which pipe to run",
    "ValidationError": "Check that spec fields match the expected schema for the given type",
    "ValueError": "Check that the provided value is valid for the parameter (e.g., --type must be a valid pipe type)",
    # Init errors
    "InitConfigError": "Check the --config JSON and ensure backend keys match available backends in the template",
    # Codegen errors
    "CodegenDriftError": (
        "Regenerate with 'pipelex-agent codegen types --target <flavor> -o <dir>' (a dev action). "
        "Check 'drifts' in this error response for the drifting artifacts and their categories."
    ),
    "CodegenLockNotFoundError": "Pass the directory that holds codegen.lock, or generate first with 'pipelex-agent codegen types'",
    "CodegenLockError": ("The codegen.lock file is unreadable or malformed — remove it, then regenerate with 'pipelex-agent codegen types'"),
    # Unknown command
    "UnknownCommandError": "Check 'valid_commands' in this error response for available commands",
}

# retryable=True fallback for non-CogtError error types: their ErrorReport
# carries no `retryable`, unlike CogtError whose error_category drives it.
RETRYABLE_ERROR_TYPES: set[str] = {
    "PipeOperatorModelAvailabilityError",
}

AGENT_ERROR_DOMAINS: dict[str, str] = {
    # input = agent can fix (bad .mthds, wrong args, bad JSON)
    "PipeValidationError": "input",
    "FixBundleError": "input",
    "FileNotFoundError": "input",
    "JSONDecodeError": "input",
    "StdinEnvelopeShapeError": "input",
    "JsonTypeError": "input",
    "TomlError": "input",
    "ArgumentError": "input",
    "ValidationError": "input",
    "ValueError": "input",
    "BundleError": "input",
    "PipelineRequestError": "input",
    "GraphSpecParseError": "input",
    "UnknownCommandError": "input",
    "CodegenDriftError": "input",
    "CodegenLockNotFoundError": "input",
    "CodegenLockError": "input",
    # config = environment/config changes needed
    "ClientAuthenticationError": "config",
    "PipeOperatorModelAvailabilityError": "config",
    "BinaryNotFoundError": "config",
    "InitConfigError": "config",
}


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


def _assemble_error_payload(message: str, *, error_type: str, cause: BaseException | None, extra: dict[str, Any]) -> dict[str, Any]:
    """Build the structured error payload shared by the JSON and markdown renderers.

    Sources ``hint`` / ``retryable`` / ``error_domain`` / ``error_category`` /
    ``model`` / ``provider`` from a ``PipelexError`` cause's ``to_error_report()``
    first, falling back to the lookup dicts for error types that cannot
    self-describe. ``extra`` is merged last and overrides everything.

    ``migration`` comes from the report too, and it is the one field here that an agent is meant
    to *act* on rather than classify by: its presence says the configuration is stale rather than
    wrong, and the loop it opens is ``pipelex-agent migrate --dry-run --format json`` followed by
    ``--yes``. Emitted only when the report carries one, so branching on its presence is the
    whole test.

    ``validation_errors`` comes from the report as well, whenever it carries any: a command that
    refuses an invalid bundle (a run refused before any pipe ran, for one) hands the agent the same
    located items ``validate`` gives, each with its pipe, its field and its fix, rather than only the
    summary sentence. They are the items :func:`extract_validation_errors` projects, dumped the same way.
    """
    error_json: dict[str, Any] = {
        "error": True,
        "error_type": error_type,
        "message": message,
    }

    # Extract structured data from PipelexError.to_error_report() when available
    report_hint: str | None = None
    report_retryable: bool | None = None
    report_category: str | None = None
    report_domain: str | None = None
    report_extras: dict[str, Any] = {}

    if isinstance(cause, PipelexError):
        report = cause.to_error_report()
        report_hint = report.user_action_detail()
        report_retryable = report.retryable
        report_category = report.error_category
        report_domain = report.error_domain
        if report.model:
            report_extras["model"] = report.model
        if report.provider:
            report_extras["provider"] = report.provider
        if report.migration is not None:
            report_extras["migration"] = report.migration.model_dump(mode="json")
        if report.validation_errors:
            report_extras["validation_errors"] = [item.model_dump(mode="json", exclude_none=True) for item in report.validation_errors]

    # hint: report-first, fallback to lookup dict
    hint = report_hint or AGENT_ERROR_HINTS.get(error_type)
    if hint:
        error_json["hint"] = hint

    # retryable: report takes precedence, fallback to lookup set (only emit when True)
    if report_retryable is not None:
        if report_retryable:
            error_json["retryable"] = True
    elif error_type in RETRYABLE_ERROR_TYPES:
        error_json["retryable"] = True

    # error_domain: report-first (class-level metadata), lookup dict as fallback
    domain = report_domain or AGENT_ERROR_DOMAINS.get(error_type)
    if domain:
        error_json["error_domain"] = domain

    # error_category: from report when available
    if report_category:
        error_json["error_category"] = report_category

    # model/provider from report
    error_json.update(report_extras)

    if cause is not None:
        error_json["error_source"] = _build_error_source(cause)

    # **extra overrides everything
    error_json.update(extra)
    return error_json


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
    """Render an assembled error payload as agent-readable markdown.

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


def _agent_error_json(message: str, *, error_type: str, cause: BaseException | None, extra: dict[str, Any], exit_code: int = 1) -> NoReturn:
    """Print a structured JSON error to stderr and exit with ``exit_code`` (default 1)."""
    payload = _assemble_error_payload(message, error_type=error_type, cause=cause, extra=extra)
    print(clean_json_dumps(payload, indent=2), file=sys.stderr)
    raise typer.Exit(exit_code) from cause


def agent_error_markdown(message: str, *, error_type: str, cause: BaseException | None = None, exit_code: int = 1, **extra: Any) -> NoReturn:
    """Print a markdown-rendered error to stderr and exit with ``exit_code`` (default 1).

    The markdown sibling of :func:`agent_error`'s JSON path: an error-type
    heading, the message body, the hint as a tip callout, and structured fields
    under a Details section. ``error_source`` (internal stack frames) is
    deliberately omitted from markdown — the field remains in the JSON envelope
    for programmatic consumers.

    Args:
        message: Human-readable error message.
        error_type: Error class name for programmatic matching.
        cause: Optional exception to chain with ``raise ... from``.
        exit_code: Process exit code. 1 (default) marks a produced negative
            verdict; 2 marks a no-verdict condition (bad args, unresolvable
            target, setup error) — the validate surface's 0/1/2 policy.
        **extra: Additional fields merged into the payload.
    """
    payload = _assemble_error_payload(message, error_type=error_type, cause=cause, extra=extra)
    print(_render_error_markdown(payload), file=sys.stderr)
    raise typer.Exit(exit_code) from cause


def agent_error(message: str, *, error_type: str, cause: BaseException | None = None, exit_code: int = 1, **extra: Any) -> NoReturn:
    """Emit a structured error to stderr and exit with ``exit_code`` (default 1).

    Dispatches on the active error format (see :func:`set_agent_cli_error_format`):
    JSON by default, markdown when a command has opted in via ``--format`` or
    ``--error-format``. All existing ``agent_error(...)`` call sites therefore
    follow the active error format for free — including sites in factory /
    unknown-command code that never see the Typer option.

    Args:
        message: Human-readable error message.
        error_type: Error class name for programmatic matching.
        cause: Optional exception to chain with ``raise ... from``.
        exit_code: Process exit code. 1 (default) marks a produced negative
            verdict; the validate commands pass 2 for no-verdict conditions
            (bad args, unresolvable target, setup error) per the 0/1/2 policy.
        **extra: Additional fields merged into the payload.
                 Can override the auto-added ``hint`` field.
    """
    match get_agent_cli_error_format():
        case CliOutputFormat.JSON:
            _agent_error_json(message, error_type=error_type, cause=cause, extra=extra, exit_code=exit_code)
        case CliOutputFormat.MARKDOWN:
            agent_error_markdown(message, error_type=error_type, cause=cause, exit_code=exit_code, **extra)


def agent_success(result: dict[str, Any]) -> None:
    """Print a structured JSON success result to stdout.

    Any pending setup warnings (e.g. a stale remote-config cache) recorded via ``record_setup_warning``
    are drained into a top-level ``warnings`` array on the envelope so machine consumers can
    surface them without parsing stderr. Callers may pre-populate ``result["warnings"]`` (must
    be a list) — the captured ones are appended. The caller's ``result`` dict is NOT mutated;
    a copy is taken before merging.

    Args:
        result: Dictionary to serialize as JSON.
    """
    captured = consume_setup_warnings()
    envelope: dict[str, Any] = result
    if captured:
        existing_raw = result.get("warnings")
        existing_warnings: list[Any] = cast("list[Any]", existing_raw) if isinstance(existing_raw, list) else []
        envelope = {**result, "warnings": [*existing_warnings, *captured]}
    print(clean_json_dumps(envelope, indent=2))


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


def run_failure_fields(*, error: PipelineExecutionError) -> dict[str, Any]:
    """The fields an agent reads off a failed run, beside the report-derived ones.

    ``pipe_code`` and ``pipe_stack`` name the pipe that failed and its path from the entry pipe.
    ``cause_type`` and ``cause_message`` are the root fault's identity and its own message, not
    those of the wrapper right under the ``PipelineExecutionError``, which is the pipe router's or
    a bridge's and says nothing about what went wrong.
    """
    fields: dict[str, Any] = {
        "pipe_code": error.pipe_code,
        "pipe_stack": error.pipe_stack,
    }
    cause = error.__cause__
    if cause is None:
        return fields
    root_fault = find_root_fault(error=cause)
    if root_fault is None:
        fields["cause_type"] = type(cause).__name__
        fields["cause_message"] = str(cause)
    else:
        root_report = root_fault.to_error_report()
        fields["cause_type"] = root_report.error_type
        fields["cause_message"] = root_report.message
    return fields


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
    """The error envelope of a request the API runner answered non-2xx, read off the problem document it sent.

    It has the shape of a local failure's envelope, so an agent reads a hosted refusal the way it reads a local one:

    - ``error_type`` is the runner's error class when the problem names one: ``ValidateBundleError`` for a bundle
      refused at load, as a local run reports it, and the root fault (``ModelNotFoundError``, ``StuffFactoryError``)
      for a run that failed, which a local run reports as ``cause_type`` under ``PipelineExecutionError``. There is
      no ``cause_type`` or ``cause_message`` on this path. ``ApiResponseError`` when the answer names no class, as a
      gateway's error page does not.
    - ``message`` is ``API POST /v1/execute failed (422): <reason>``, the error's own message without the next step
      it appends, which ``hint`` carries. On a failed run the runner's reason is located at the failing pipe and its
      path, ``Pipe 'condense_article' failed (digest_article → condense_article): …``.
    - ``hint`` is the runner's next step, ``user_action.detail``. An answer that advised none, such as the ones a
      hosted plane authors in front of the runner (a refused key, a rate limit, a runner it cannot reach), gets the
      hint of its status from ``API_REFUSAL_HINTS_BY_STATUS``, else a hint by status class (a 4xx asks for a change to
      the request, anything else for a report); never the hint keyed on the runner's class, which names a local
      command that cannot fix a remote refusal.
    - ``retryable`` (only when true, as on every envelope), ``error_domain`` and ``error_category`` are the answer's,
      with no local fallback, since only the runner knows whether the caller or its operator has to act. The one
      exception is ``retryable`` on a 429 that did not say, a refusal sent before anything ran. A 503 is never
      inferred retryable: a hosted plane can answer it after the run completed.
    - ``validation_errors`` are the runner's items, each whole, as it sent them.
    - ``pipe_code`` and ``pipe_stack`` when the problem carries them as members.
    - ``error_code`` is the problem's ``code`` member, the stable code a hosted plane gives its own refusals
      (``rate_limited``, ``unauthorized``), and ``retry_after_seconds`` the ``Retry-After`` header's delay.
    - ``http_status`` and ``request_id`` are what to quote when the fault is the runner's.
    - ``error_source`` is the client-side trace, as on every JSON envelope.
    """
    problem: dict[str, Any] = error.problem or {}
    message = str(error)
    hint: str
    if error.user_action is None:
        hint = API_REFUSAL_HINTS_BY_STATUS.get(error.status) or (
            API_REFUSAL_CALLER_HINT if 400 <= error.status < 500 else AGENT_ERROR_HINTS["ApiResponseError"]
        )
    else:
        hint = error.user_action.detail
        message = message.removesuffix(f"\nNext step: {hint}")

    payload: dict[str, Any] = {
        "error": True,
        "error_type": error.error_type or type(error).__name__,
        "message": message,
        "hint": hint,
    }
    if error.retryable or (error.retryable is None and error.status in _API_RETRYABLE_STATUSES):
        payload["retryable"] = True
    if error.error_domain:
        payload["error_domain"] = error.error_domain
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
    """Emit the envelope of a request the API runner refused to stderr, format-aware, and exit 1.

    The sibling of :func:`agent_error` for the one error an API runner's refusal arrives as. It builds its own
    payload rather than going through :func:`agent_error`'s lookups, whose fallbacks keyed on ``error_type`` are
    local advice (see :func:`api_response_error_payload`), and renders it with the same JSON dump and the same
    markdown renderer, so a hosted refusal reads like a local failure.

    Args:
        error: The refusal the ``MthdsAPIClient`` raised.
    """
    payload = api_response_error_payload(error=error)
    match get_agent_cli_error_format():
        case CliOutputFormat.JSON:
            print(clean_json_dumps(payload, indent=2), file=sys.stderr)
        case CliOutputFormat.MARKDOWN:
            print(_render_error_markdown(payload), file=sys.stderr)
    raise typer.Exit(1) from error


def extract_validation_errors(exc: ValidateBundleError) -> list[dict[str, Any]]:
    """Project a ``ValidateBundleError`` into the CLI ``validation_errors`` JSON array.

    Thin adapter over ``ValidateBundleError.validation_error_items`` — the shared builder,
    same one feeding the API 422's ``ErrorReport.validation_errors`` — so the CLI
    and API structured shapes can never drift. Each typed item is dumped to a
    plain dict with unset fields dropped (``exclude_none``), matching the
    machine-first agent-CLI envelope; the entries carry ``category``,
    ``error_type``, ``message``, and whatever identity / ``source`` fields the
    underlying error populated. Each pipe whose dry run failed becomes its own
    located ``dry_run`` item, and a parse-level failure that carries only a
    message becomes one ``blueprint_validation`` residual. So the envelope's
    ``validation_errors[]`` is non-empty on every invalid verdict (the
    structured-info invariant) — never a bare message.

    Args:
        exc: The ValidateBundleError to extract errors from.

    Returns:
        List of dicts, each with at minimum ``category`` and ``message``.
    """
    return [item.model_dump(mode="json", exclude_none=True) for item in exc.validation_error_items()]


def _render_validate_bundle_markdown(
    items: list[ValidationErrorItem],
    *,
    bundle_path: Path,
    library_dirs: list[Path] | None,
    allow_signatures: bool,
) -> str:
    """Compose the agent ``validate`` failure markdown: heading, bundle, prose items, fix-aware footer.

    Mirrors the human ``handle_validate_bundle_error`` panel: the structured items become prose
    (via the shared :func:`format_validation_error_items_markdown`) rather than a JSON dump, and
    the footer either names the exact ``pipelex-agent fix bundle`` command when items carry a
    suggested fix, or points at the messages above when nothing is auto-fixable. Doc/Discord
    links are deliberately dropped — they are noise for an LLM fixing a ``.mthds`` file.
    """
    lines: list[str] = ["# Bundle validation failed", "", f"**Bundle:** `{bundle_path}`", "", format_validation_error_items_markdown(items)]

    # A hint needs an action behind it (disease E): when items carry a suggested fix, name the exact
    # fix command — same predicate and command shape as the human footer — instead of the boilerplate
    # class-level hint that the JSON envelope keeps.
    fixable_count = count_applicable_fixes(items, bundle_path=bundle_path, library_dirs=library_dirs)
    if fixable_count:
        fix_command = build_fix_command(
            executable="pipelex-agent", bundle_path=bundle_path, library_dirs=library_dirs, allow_signatures=allow_signatures
        )
        lines += ["", f"💡 {fixable_count} of these errors can be fixed automatically — run: `{fix_command}`"]
    else:
        lines += ["", "💡 These errors have no automatic fix — review the messages above and edit the bundle."]
    return "\n".join(lines)


def agent_error_validate_bundle(
    exc: ValidateBundleError,
    *,
    bundle_path: Path,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = False,
) -> NoReturn:
    """Emit an agent-CLI bundle-validation failure to stderr, format-aware, and exit 1.

    The dedicated dispatcher for the ``validate`` invalid verdict (the sibling of
    :func:`agent_error` for this one error type). It keeps the two streams honest to the
    workspace's "format follows consumer" doctrine:

    - **markdown** renders the structured items as prose with per-item ``💡 Suggested fix`` lines
      and a fix-aware footer, mirroring the human ``handle_validate_bundle_error`` panel;
    - **JSON** emits the *exact same* structured envelope as before — ``is_valid`` / ``bundle_path``
      / ``validation_errors`` — because software consumers (hooks pin ``--format json``) branch on
      those structured fields; the machine contract must not change.

    Args:
        exc: The bundle-validation failure to report.
        bundle_path: The bundle file / pipeline directory that failed validation.
        library_dirs: The ``-L/--library-dir`` values, echoed into the markdown fix-command footer.
        allow_signatures: Whether the invocation accepted ``PipeSignature`` placeholders; echoed into
            the markdown fix-command footer so the suggested fix keeps the same leniency.
    """
    match get_agent_cli_error_format():
        case CliOutputFormat.JSON:
            _agent_error_json(
                exc.message,
                error_type="ValidateBundleError",
                cause=exc,
                extra={"is_valid": False, "bundle_path": str(bundle_path), "validation_errors": extract_validation_errors(exc)},
                exit_code=1,
            )
        case CliOutputFormat.MARKDOWN:
            items = list(exc.to_error_report().validation_errors or [])
            markdown = _render_validate_bundle_markdown(items, bundle_path=bundle_path, library_dirs=library_dirs, allow_signatures=allow_signatures)
            print(markdown, file=sys.stderr)
            raise typer.Exit(1) from exc
