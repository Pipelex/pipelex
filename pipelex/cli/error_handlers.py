from contextvars import ContextVar
from enum import StrEnum
from pathlib import Path
from typing import NoReturn

import click
import typer
from rich.console import Console
from rich.markup import escape
from rich.traceback import Traceback

from pipelex.base_exceptions import ErrorDomain, PipelexConfigError, PipelexError, ValidationErrorCategory, ValidationErrorItem, iter_cause_chain
from pipelex.cogt.exceptions import ModelDeckPresetValidationError
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.errors.failure_problem import failure_problem, format_problem_location, format_problem_verdict
from pipelex.errors.problem import PipelexProblem, ProblemView, cap_problem_text
from pipelex.migration.exceptions import FormerReleaseConfigError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validation_render import build_fix_command, count_applicable_fixes, suggested_fix_label, validation_item_title
from pipelex.runtime_hub import get_error_console
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.urls import URLs


class ErrorContext(StrEnum):
    """Context for error messages in CLI commands."""

    PIPE_RUN = "Pipe run"
    VALIDATION = "Pipe validation"
    FIX = "Bundle fix"
    BUILD = "Pipe build"

    # Pre-validation contexts (for Pipelex.make() errors)
    VALIDATION_BEFORE_SHOW_PIPES = "Pre-validation (show pipes)"
    VALIDATION_BEFORE_SHOW_PIPE = "Pre-validation (show pipe)"
    VALIDATION_BEFORE_SHOW_MODELS = "Pre-validation (show models)"
    VALIDATION_BEFORE_SHOW_BACKENDS = "Pre-validation (show backends)"
    VALIDATION_BEFORE_PIPE_RUN = "Pre-validation (pipe run)"
    VALIDATION_BEFORE_BUILD_INPUTS = "Pre-validation (build inputs)"
    VALIDATION_BEFORE_BUILD_OUTPUT = "Pre-validation (build output)"
    KIT = "Kit operation"


# Whether --traceback was passed, recorded at parse time by PipelexCLI.make_context.
# This is a ContextVar (mirroring set_agent_cli_error_format) rather than a read of the
# global Click context: typer >= 0.26 / click >= 8.4 do not push a global context during
# subcommand dispatch, so reading the flag there silently lost it on handled errors.
_traceback_requested: ContextVar[bool] = ContextVar("pipelex_cli_traceback_requested", default=False)


def _advice_detail(*, error: PipelexError) -> str | None:
    """The advice nearest the error along its cause chain, which a panel prints as its tip; ``None`` when none advises."""
    advised_action = error.advised_action()
    if advised_action is None or not advised_action.detail:
        return None
    return advised_action.detail


def set_traceback_requested(*, value: bool) -> None:
    """Record whether --traceback was passed, independent of the Click context."""
    _traceback_requested.set(value)


def is_traceback_requested() -> bool:
    """Check whether the --traceback global flag was passed on the CLI invocation."""
    # Authoritative path: the flag recorded at parse time, context-independent.
    if _traceback_requested.get():
        return True
    # Fallback for callers that push a Click context directly (tests / embedders).
    try:
        ctx = click.get_current_context(silent=True)
    except RuntimeError:
        return False
    if ctx is None:
        return False
    obj = ctx.find_root().obj
    if obj is None:
        return False
    return bool(obj.get("traceback", False))


def print_traceback_if_requested(*, console: Console) -> None:
    """Print a Rich traceback of the current exception when --traceback is active."""
    if is_traceback_requested():
        console.print(Traceback())


def problem_panel_fields(
    *, problem: PipelexProblem, error_message: str | None, tip: str | None, with_next_step: bool = True
) -> list[tuple[str, str]]:
    """The rows a panel prints for its problem, their values escaped for Rich.

    The problem's title, its detail when neither the title nor the error message already says it, its next step when the tip does
    not, its code with the domain and the retry verdict, then where it happened, the request and the run when known.

    Args:
        problem: The problem the panel reports, in the operator's view.
        error_message: The error message the panel prints, as printed (escaped), or ``None`` when it prints none.
        tip: The tip the panel prints, as printed (escaped or markup), or ``None`` when it prints none.
        with_next_step: Whether to print the code's next step, which a panel whose own remedy names the command that
            applies leaves out.

    Returns:
        ``(label, value)`` pairs, the values already escaped.
    """
    rows: list[tuple[str, str]] = [("Problem", escape(problem.title))]
    detail = escape(problem.detail)
    if detail and detail not in {error_message, escape(problem.title)}:
        rows.append(("Detail", detail))
    next_step = escape(problem.next_step.detail)
    if with_next_step and next_step and next_step != tip:
        rows.append(("Next step", next_step))
    rows.append(("Code", f"[yellow]{escape(problem.code)}[/yellow] [dim]({escape(format_problem_verdict(problem=problem))})[/dim]"))
    where = format_problem_location(location=problem.location)
    if where:
        rows.append(("Location", escape(where)))
    if problem.request_id:
        rows.append(("Request id", escape(problem.request_id)))
    if problem.pipeline_run_id:
        rows.append(("Run", escape(problem.pipeline_run_id)))
    return rows


def _print_panel_rows(*, console: Console, rows: list[tuple[str, str]]) -> None:
    """Print ``(label, value)`` rows with their labels padded to a common width, so the values line up."""
    label_width = max((len(label) for label, _ in rows), default=0)
    for label, value in rows:
        padded_label = f"{label}:".ljust(label_width + 1)
        console.print(f"[bold cyan]{padded_label}[/bold cyan] {value}")


def print_problem_rows(*, console: Console, problem: PipelexProblem, error_message: str | None, tip: str | None, with_next_step: bool = True) -> None:
    """Print a panel's problem rows (:func:`problem_panel_fields`), followed by a blank line.

    Args:
        console: The console to print to.
        problem: The problem the panel reports, in the operator's view.
        error_message: The error message the panel prints, as printed (escaped), or ``None``.
        tip: The tip the panel prints, as printed (escaped or markup), or ``None``.
        with_next_step: Whether to print the code's next step.
    """
    rows = problem_panel_fields(problem=problem, error_message=error_message, tip=tip, with_next_step=with_next_step)
    _print_panel_rows(console=console, rows=rows)
    console.print()


def print_problem_items(*, console: Console, problem: PipelexProblem) -> None:
    """Print a problem's faults, its ``errors``, one per line with its code, its sentence and where, then a blank line.

    Nothing is printed for a problem that lists none.

    Args:
        console: The console to print to.
        problem: The problem whose faults to print.
    """
    if not problem.errors:
        return
    console.print("[bold cyan]Errors:[/bold cyan]")
    for item in problem.errors:
        where = format_problem_location(location=item.location)
        located = f" ({where})" if where else ""
        console.print(f"  - [yellow]{escape(item.code)}[/yellow]: {escape(item.detail + located)}")
    console.print()


def print_failure_problem(*, console: Console, title: str, error: BaseException) -> PipelexProblem:
    """Print a command's own report of a failure it caught at its root, and return the failure's problem.

    The title, then the error's message: a Pipelex error's own, or, for an exception that is no Pipelex error, its type
    and its message capped as the operator view caps it. Then the problem's rows and the advice the error's chain gives
    as a tip. This report is the CLI's output, not a log record, so the terminal names the cause whatever the sink and
    the level: under the `json` sink writing to a file, or a level above ERROR, it is the only place the person running
    the command reads it. The log line the caller writes carries the problem's code and the chain's classes, never a
    message (:func:`pipelex.errors.failure_problem.failure_log_fields`), and a traceback only under ``--traceback``.

    Args:
        console: The console to print to.
        title: The headline, which names what failed.
        error: What the command caught.

    Returns:
        The failure's problem, in the operator's view, for the caller's log line.
    """
    problem = failure_problem(error=error)
    message: str
    advice: str | None
    if isinstance(error, PipelexError):
        message = error.message
        advice = _advice_detail(error=error)
    else:
        exception_text = cap_problem_text(text=str(error))
        message = f"{type(error).__name__}: {exception_text}" if exception_text else type(error).__name__
        advice = None
    # The message and the advice are plain text, a type such as `list[int]` or a model's description such as
    # `SDK[openai]` included, so they are escaped before Rich reads markup in them.
    printed_message = escape(message)
    printed_tip = escape(advice) if advice is not None else None
    console.print(f"\n[bold red]{escape(title)}[/bold red]\n")
    console.print(f"  {printed_message}\n")
    print_problem_rows(console=console, problem=problem, error_message=printed_message, tip=printed_tip)
    if printed_tip is not None:
        console.print(f"[bold green]💡 Tip:[/bold green] {printed_tip}\n")
    return problem


def display_error_panel(
    *,
    console: Console,
    title: str,
    fields: list[tuple[str, str]],
    error_message: str | None,
    problem: PipelexProblem | None,
    tip: str,
    links: list[tuple[str, str]],
) -> None:
    """Print the canonical CLI error panel.

    Layout: a red ❌ banner, an aligned block of structured fields, the error
    message, the problem's rows (title, detail, next step, code, location,
    request id), a 💡 tip, and dimmed help links. Field labels are right-padded
    to a common width so the values line up.

    Exception-specific logic (which fields to include, what tip to derive)
    stays in each ``handle_*`` function; this helper owns only the panel shape.

    Args:
        console: Rich console to print to.
        title: Headline text after the ❌ (already markup-safe).
        fields: ``(label, value)`` pairs; values must already be escaped.
        error_message: The error message body (already markup-safe), or None to omit it.
        problem: The problem the panel reports, in the operator's view, or None to print no problem rows.
        tip: The 💡 tip text, printed as given: already markup-safe, its plain text escaped by the caller (it may
            span several lines and carry markup the caller meant).
        links: ``(label, url)`` pairs printed dimmed at the bottom.
    """
    console.print(f"\n[bold red]❌ {title}[/bold red]\n")
    _print_panel_rows(console=console, rows=fields)
    if error_message is not None:
        console.print(f"\n[bold red]Error:[/bold red] {error_message}\n")
    elif fields:
        console.print()
    if problem is not None:
        print_problem_rows(console=console, problem=problem, error_message=error_message, tip=tip)
    # The tip is printed as given: its caller escaped the plain text in it and kept the markup it meant.
    console.print(f"[bold green]💡 Tip:[/bold green] {tip}")
    for link_label, link_url in links:
        console.print(f"[dim]{link_label}: {link_url}[/dim]")
    console.print()


def handle_model_choice_error(exc: PipeOperatorModelChoiceError, *, context: ErrorContext, exit_code: int = 1) -> NoReturn:
    """Handle and display PipeOperatorModelChoiceError with formatted output.

    Args:
        exc: The model choice error exception
        context: Context for the error message
        exit_code: Process exit code; the default is 1. The validate surface never reaches
            this handler: an unknown model is an invalid verdict there, rendered by
            :func:`handle_validate_bundle_error`.
    """
    console = get_error_console()
    print_traceback_if_requested(console=console)
    tip = _advice_detail(error=exc) or (
        f"Check your model configuration in .pipelex/inference/ or specify a different model in the '{exc.pipe_code}' pipe."
    )
    display_error_panel(
        console=console,
        title=f"{context} failed because of a model choice could not be interpreted correctly",
        fields=[
            ("Pipe", f"[yellow]'{escape(exc.pipe_code)}'[/yellow] [dim]({escape(exc.pipe_type)})[/dim]"),
            ("Model Type", f"[yellow]'{escape(exc.model_type)}'[/yellow]"),
            ("Model Choice", f"[yellow]'{escape(str(exc.model_choice))}'[/yellow]"),
        ],
        error_message=escape(exc.message),
        problem=exc.to_problem(view=ProblemView.OPERATOR),
        tip=escape(tip),
        links=[
            ("Learn more about the inference backend system", URLs.backend_provider_docs),
            ("Join our Discord for help", URLs.discord),
        ],
    )
    raise typer.Exit(exit_code) from exc


def handle_model_availability_error(exc: PipeOperatorModelAvailabilityError, *, context: ErrorContext, exit_code: int = 1) -> NoReturn:
    """Handle and display PipeOperatorModelAvailabilityError with formatted output.

    Args:
        exc: The model availability error exception
        context: Context for the error message
        exit_code: Process exit code. The validate surface passes 2: a model the deck defines
            but no enabled backend serves is a setup fault of this machine, so no verdict, unlike
            an unknown model, which is an invalid verdict there. Other contexts keep the default 1.
    """
    console = get_error_console()
    print_traceback_if_requested(console=console)
    fields: list[tuple[str, str]] = [
        ("Pipe", f"[yellow]'{escape(exc.pipe_code)}'[/yellow] [dim]({escape(exc.pipe_type)})[/dim]"),
        ("Model", f"[yellow]'{escape(exc.model_handle or '')}'[/yellow]"),
    ]
    if exc.fallback_list:
        fallbacks_str = ", ".join([f"[yellow]{escape(fallback)}[/yellow]" for fallback in exc.fallback_list])
        fields.append(("Fallbacks", fallbacks_str))
    if len(exc.pipe_stack) > 1:
        stack_str = " [dim]→[/dim] ".join([f"[yellow]{escape(stacked_pipe)}[/yellow]" for stacked_pipe in exc.pipe_stack])
        fields.append(("Pipe Stack", stack_str))
    # The local-deck remedy is given here and nowhere else: the model error's own message reaches
    # every surface, hosted ones included, whose readers have no local deck to refresh.
    local_deck_remedy = (
        "Your local model deck may be out of date: new aliases and presets are added to Pipelex over time, and existing "
        "'.pipelex/inference/deck/*.toml' files are not refreshed automatically. To pick up the latest definitions, delete "
        "your local deck files under '.pipelex/inference/deck/' (or the whole '.pipelex/inference/' directory) and run "
        "'pipelex init inference' to regenerate them.\n"
        "If that does not resolve it, make sure the handle is defined in one of '.pipelex/inference/deck/*.toml', that the "
        "backend it routes to (see '.pipelex/inference/routing_profiles.toml') is enabled in '.pipelex/inference/backends.toml', "
        "and that you have the necessary credentials"
    )
    user_action_detail = _advice_detail(error=exc)
    tip: str
    if user_action_detail is None:
        tip = f"{local_deck_remedy}, or specify a different model in the '{exc.pipe_code}' pipe."
    elif ErrorDomain.from_problem_domain(exc.resolve_domain()).is_input:
        # The method named a model no entry of the deck names, and the lookup's next step is to
        # change it. A local deck can also be what lacks that model, so the local remedy follows.
        tip = f"{user_action_detail}\n{local_deck_remedy}."
    else:
        tip = user_action_detail
    display_error_panel(
        console=console,
        title=f"{context} failed because a model wasn't available",
        fields=fields,
        error_message=escape(str(exc)),
        problem=exc.to_problem(view=ProblemView.OPERATOR),
        tip=escape(tip),
        links=[
            ("Learn more about the inference backend system", URLs.backend_provider_docs),
            ("Join our Discord for help", URLs.discord),
        ],
    )
    raise typer.Exit(exit_code) from exc


def handle_dedicated_failure_panel(*, error: BaseException, context: ErrorContext) -> None:
    """Render the dedicated panel of the first error on `error`'s cause chain that has one, and exit.

    A run failure reaches the CLI as a `PipelineExecutionError` around the located failure, so a
    handler written for the model errors never matches it directly: this walks the cause chain for
    them, and the panel then names the pipe that failed, the model and the stack. Returns without
    printing anything when no error on the chain has a dedicated panel.
    """
    for node in iter_cause_chain(error):
        if isinstance(node, PipeOperatorModelAvailabilityError):
            handle_model_availability_error(node, context=context)
        if isinstance(node, PipeOperatorModelChoiceError):
            handle_model_choice_error(node, context=context)


def handle_model_deck_preset_error(exc: ModelDeckPresetValidationError, *, context: ErrorContext) -> NoReturn:
    """Handle and display ModelDeckPresetValidationError with formatted output.

    Args:
        exc: The model deck preset validation error exception
        context: Context for the error message
    """
    console = get_error_console()
    print_traceback_if_requested(console=console)
    model_handle = exc.model_handle or ""
    fields: list[tuple[str, str]] = [
        ("Preset ID", f"[yellow]'{escape(exc.preset_id)}'[/yellow]"),
        ("Model Type", f"[yellow]'{escape(exc.model_type)}'[/yellow]"),
        ("Model Handle", f"[yellow]'{escape(model_handle)}'[/yellow]"),
    ]
    if exc.enabled_backends:
        backends_str = ", ".join([f"[yellow]{escape(backend)}[/yellow]" for backend in sorted(exc.enabled_backends)])
        fields.append(("Enabled Backends", backends_str))

    tip_detail = _advice_detail(error=exc)
    if tip_detail is not None:
        tip = escape(tip_detail)
    else:
        tip_lines: list[str] = [
            (
                f"The preset [yellow]'{escape(exc.preset_id)}'[/yellow] references model handle "
                f"[yellow]'{escape(model_handle)}'[/yellow] which is not available in any enabled backend."
            )
        ]
        if exc.enabled_backends:
            backends_str = ", ".join([f"[yellow]{escape(backend)}[/yellow]" for backend in sorted(exc.enabled_backends)])
            tip_lines.append(f"The enabled backends are: {backends_str}.")
        tip_lines.append(
            "[bold]Possible solutions:[/bold]\n"
            "  1. Update the preset to use a different model\n"
            f"  2. Configure model '{escape(model_handle)}' in one of your enabled backends\n"
            f"  3. Enable a backend that supports [yellow]'{escape(model_handle)}'[/yellow]"
        )
        tip = "\n".join(tip_lines)

    display_error_panel(
        console=console,
        title=f"{context} failed due to model deck preset validation error",
        fields=fields,
        error_message=escape(exc.message),
        problem=exc.to_problem(view=ProblemView.OPERATOR),
        tip=tip,
        links=[
            ("Learn more about the inference backend system", URLs.backend_provider_docs),
            ("Join our Discord for help", URLs.discord),
        ],
    )
    raise typer.Exit(1) from exc


def _validation_category_header(category: ValidationErrorCategory) -> str:
    match category:
        case ValidationErrorCategory.BLUEPRINT_VALIDATION:
            return "Blueprint Validation Errors:"
        case ValidationErrorCategory.PIPE_FACTORY:
            return "Pipe Factory Errors:"
        case ValidationErrorCategory.PIPE_VALIDATION:
            return "Pipe Validation Errors:"
        case ValidationErrorCategory.DRY_RUN:
            return "Dry Run Errors:"


def _display_validation_error_item(*, console: Console, item: ValidationErrorItem, error_index: int) -> None:
    """Render one structured validation-error item: title, identity fields, message, fix, locators."""
    console.print(f"[bold yellow]{error_index}. {escape(validation_item_title(item=item))}[/bold yellow]")

    if item.pipe_code:
        console.print(f"   [cyan]Pipe:[/cyan] [yellow]{escape(item.pipe_code)}[/yellow]")
    if item.concept_code:
        console.print(f"   [cyan]Concept:[/cyan] [yellow]{escape(item.concept_code)}[/yellow]")
    if item.domain_code:
        console.print(f"   [cyan]Domain:[/cyan] [green]{escape(item.domain_code)}[/green]")
    if item.field_name:
        console.print(f"   [cyan]Field:[/cyan] [yellow]{escape(item.field_name)}[/yellow]")
    if item.missing_concept_code:
        console.print(f"   [cyan]Missing Concept:[/cyan] [yellow]{escape(item.missing_concept_code)}[/yellow]")
    if item.missing_pipe_code:
        console.print(f"   [cyan]Missing Pipe:[/cyan] [yellow]{escape(item.missing_pipe_code)}[/yellow]")
    if item.declared_concepts:
        declared_str = ", ".join([f"[yellow]{escape(concept_code)}[/yellow]" for concept_code in item.declared_concepts])
        console.print(f"   [cyan]Declared Concepts:[/cyan] {declared_str}")
    if item.variable_names:
        variables_str = ", ".join([f"[yellow]{escape(variable_name)}[/yellow]" for variable_name in item.variable_names])
        console.print(f"   [cyan]Variables:[/cyan] {variables_str}")

    console.print(f"   [cyan]→[/cyan] {escape(item.message)}")

    if item.suggested_fix is not None:
        # The words carry the safety, so the colour only echoes them: an unsafe fix is yellow because
        # it needs the reader's confirmation, a safe one green because `pipelex fix bundle` applies it.
        fix_style = "green" if item.suggested_fix.safety.is_safe else "yellow"
        fix_label = escape(suggested_fix_label(fix=item.suggested_fix))
        console.print(f"   [{fix_style}]💡 {fix_label}:[/{fix_style}] {escape(item.suggested_fix.description)}")

    if item.field_path:
        console.print(f"   [dim]└─ Path: {escape(item.field_path)}[/dim]")
    if item.source:
        console.print(f"   [dim]└─ Source: {escape(item.source)}[/dim]")

    console.print()


def display_validation_error_items(*, console: Console, items: list[ValidationErrorItem]) -> None:
    """Render structured validation-error items grouped by category, with per-item suggested fixes.

    The single human renderer for bundle-validation diagnostics — used by ``pipelex validate``
    (via :func:`handle_validate_bundle_error`) and by ``pipelex fix``'s still-invalid arm
    (``remaining_errors``), so the two commands cannot drift. Items come from the shared
    ``build_validation_error_items`` builder, which is also what attaches ``suggested_fix``.
    """
    items_by_category: dict[ValidationErrorCategory, list[ValidationErrorItem]] = {}
    for item in items:
        items_by_category.setdefault(item.category, []).append(item)

    for category in ValidationErrorCategory:
        category_items = items_by_category.get(category, [])
        if not category_items:
            continue
        console.print(f"[bold cyan]{_validation_category_header(category)}[/bold cyan]\n")
        # Every category, dry run included, renders numbered items: a dry-run item is located on its
        # failing pipe like any other, so it names the pipe, the domain and the source.
        for error_index, item in enumerate(category_items, 1):
            _display_validation_error_item(console=console, item=item, error_index=error_index)


def handle_validate_bundle_error(
    exc: ValidateBundleError,
    *,
    bundle_path: Path | None = None,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = False,
) -> NoReturn:
    """Handle and display ValidateBundleError with formatted output.

    Args:
        exc: The bundle validation error exception
        bundle_path: Optional path to the bundle file being validated
        library_dirs: The ``-L/--library-dir`` values of the invocation, echoed into the
            actionable ``pipelex fix bundle`` footer so the suggested command reproduces the
            same write scope
        allow_signatures: Whether the invocation accepted PipeSignature placeholders; when true,
            the actionable fix command preserves the same leniency.
    """
    items = exc.validation_error_items()
    console = get_error_console()
    print_traceback_if_requested(console=console)
    console.print("\n[bold red]❌ Bundle validation failed[/bold red]\n")

    if bundle_path:
        console.print(f"[bold cyan]Bundle:[/bold cyan] [yellow]{escape(str(bundle_path))}[/yellow]\n")

    display_validation_error_items(console=console, items=items)

    # A hint needs an action behind it: when fixes exist, the actionable footer replaces the
    # generic tip (two stacked 💡 tips would be noise).
    fixable_count = count_applicable_fixes(items, bundle_path=bundle_path, library_dirs=library_dirs) if bundle_path is not None else 0
    problem = exc.to_problem(view=ProblemView.OPERATOR)
    if fixable_count and bundle_path is not None:
        print_problem_rows(console=console, problem=problem, error_message=None, tip=None)
        # Shared builder so the human and agent fix-command footers echo -L / --allow-signatures identically.
        fix_command = build_fix_command(executable="pipelex", bundle_path=bundle_path, library_dirs=library_dirs, allow_signatures=allow_signatures)
        console.print(
            f"[bold green]💡 {fixable_count} of these errors can be fixed automatically[/bold green] — run: [cyan]{escape(fix_command)}[/cyan]"
        )
    else:
        tip = _advice_detail(error=exc) or (
            "Review the error messages above and check your pipeline configuration. "
            "Make sure all required fields are present and correctly formatted."
        )
        # The advice is plain text, a model's description such as `SDK[openai]` included, escaped once for Rich.
        printed_tip = escape(tip)
        print_problem_rows(console=console, problem=problem, error_message=None, tip=printed_tip)
        console.print(f"[bold green]💡 Tip:[/bold green] {printed_tip}")
    console.print(f"[dim]Learn more: {URLs.documentation}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_pre_boot_config_error(*, exc: PipelexConfigError, command: str, exit_code: int) -> NoReturn:
    """Report a configuration that cannot be read before the boot, naming the command, never as a traceback.

    A command handed a method's folder or bundle file lists its method tree before it boots, under the limits the
    configuration sets, so a configuration the boot would refuse is refused there first. It is reported as
    `Failed to <command>:` and the refusal, which names what to fix and the migration that would.

    Args:
        exc: The configuration's refusal.
        command: The human command name, as the command's other failures name it (e.g. ``"validate"``).
        exit_code: The exit code the command gives this refusal. ``validate`` and ``fix`` give 2, since it gives no
            verdict on the method, as the 0/1/2 policy reserves 2 for, and the agent CLI's ``validate bundle`` and
            ``fix bundle`` give the same; ``run`` and ``build`` give 1, as they give their other failures. ``validate``
            and ``fix`` do not list a lone ``.mthds`` file before the boot, so for a file the same configuration
            surfaces only at the boot, which exits 1.
    """
    print_traceback_if_requested(console=get_error_console())
    typer.secho(f"Failed to {command}: {exc.message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(exit_code) from exc


def handle_telemetry_config_validation_error(exc: TelemetryConfigValidationError) -> NoReturn:
    """Handle and display TelemetryConfigValidationError, saying whether the file is old or wrong.

    This used to announce a breaking change and send every reader to ``pipelex init telemetry``,
    which was written for one real event — the flat pre-``[custom_posthog]`` format — and then
    kept being shown for every other way a telemetry file can fail. The ledger now carries that
    format forward on its own, so a file reaching here is either one the ledger cannot fully
    explain or one that is genuinely invalid, and telling either reader to regenerate the file
    would throw away the keys and exporters in it.

    What the error itself carries is the answer: the fields the model refused, and a migration
    block when a scan found something a ``pipelex migrate`` would do.

    Args:
        exc: The telemetry config validation error exception
    """
    console = get_error_console()
    print_traceback_if_requested(console=console)
    console.print("\n[bold red]❌ Telemetry configuration could not be loaded[/bold red]\n")

    console.print(escape(exc.message))
    console.print()
    # The remedy below names the command that applies, which the code's generic next step does not.
    print_problem_rows(console=console, problem=exc.to_problem(view=ProblemView.OPERATOR), error_message=None, tip=None, with_next_step=False)

    if exc.migration is not None and exc.migration.would_write:
        console.print(f"[bold green]💡 To fix:[/bold green] Run [cyan]{exc.migration.remedy}[/cyan] to bring your configuration up to date\n")
        console.print("[dim]The migration keeps every setting in the file — it does not start it over.[/dim]")
    elif exc.migration is not None:
        # A block whose `would_write` is False is a diagnosis, not a repair: the command would visit
        # this file, write nothing, and leave the same refusal standing. What the reader needs is the
        # dry run's detail and their own editor.
        console.print("[bold green]💡 To fix:[/bold green] Correct the settings named above in [cyan]telemetry.toml[/cyan]\n")
        console.print(f"[dim]Run [cyan]{exc.migration.remedy} --dry-run[/cyan] for what the migration found — it would rewrite nothing here.[/dim]")
    else:
        console.print("[bold green]💡 To fix:[/bold green] Correct the settings named above in [cyan]telemetry.toml[/cyan]\n")
        console.print("[dim]Or run [cyan]pipelex init telemetry[/cyan] to start the file over — this discards what is in it.[/dim]")
    console.print()

    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_former_release_config_error(*, exc: FormerReleaseConfigError) -> NoReturn:
    """Handle the boot's refusal of a configuration a former release set up for the Pipelex Gateway.

    The message is the whole answer: it names what stops the boot, file by file, and the remedies, `pipelex migrate`
    and `pipelex init`. A traceback would bury it, and any advice added here would repeat it.

    Args:
        exc: The former release configuration error.
    """
    console = get_error_console()
    print_traceback_if_requested(console=console)
    console.print("\n[bold red]❌ Configuration left by a former release[/bold red]\n")
    console.print(escape(exc.message))
    console.print()
    # The message names the remedies, which the code's generic next step does not.
    print_problem_rows(console=console, problem=exc.to_problem(view=ProblemView.OPERATOR), error_message=None, tip=None, with_next_step=False)
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc
