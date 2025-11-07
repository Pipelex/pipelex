"""Helper functions for handling and displaying CLI errors."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, NoReturn

import typer
from rich.console import Console
from rich.syntax import Syntax

from pipelex.urls import URLs

if TYPE_CHECKING:
    from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
    from pipelex.core.validation_errors import PipelexValidationExceptionAbstract
    from pipelex.exceptions import PipeOperatorModelAvailabilityError, PipeOperatorModelChoiceError


class ErrorContext(StrEnum):
    """Context for error messages in CLI commands."""

    PIPE_RUN = "Pipe run"
    VALIDATION = "Pipe validation"
    BUILD = "Pipe build"

    # Pre-validation contexts (for Pipelex.make() errors)
    VALIDATION_BEFORE_SHOW_PIPES = "Pre-validation (show pipes)"
    VALIDATION_BEFORE_SHOW_PIPE = "Pre-validation (show pipe)"
    VALIDATION_BEFORE_SHOW_MODELS = "Pre-validation (show models)"
    VALIDATION_BEFORE_SHOW_BACKENDS = "Pre-validation (show backends)"
    VALIDATION_BEFORE_PIPE_RUN = "Pre-validation (pipe run)"
    VALIDATION_BEFORE_BUILD_PIPE = "Pre-validation (build pipe)"
    VALIDATION_BEFORE_BUILD_RUNNER = "Pre-validation (build runner)"
    VALIDATION_BEFORE_BUILD_INPUTS = "Pre-validation (build inputs)"
    VALIDATION_BEFORE_BUILD_ONE_SHOT = "Pre-validation (build one-shot)"
    VALIDATION_BEFORE_BUILD_PARTIAL = "Pre-validation (build partial)"


def handle_model_choice_error(exc: PipeOperatorModelChoiceError, context: ErrorContext) -> NoReturn:
    """Handle and display PipeOperatorModelChoiceError with formatted output.

    Args:
        exc: The model choice error exception
        context: Context for the error message
    """
    console = Console(stderr=True)
    console.print(f"\n[bold red]❌ {context} failed because of a model choice could not be interpreted correctly[/bold red]\n")
    console.print(f"[bold cyan]Pipe:[/bold cyan]         [yellow]'{exc.pipe_code}'[/yellow] [dim]({exc.pipe_type})[/dim]")
    console.print(f"[bold cyan]Model Type:[/bold cyan]   [yellow]'{exc.model_type}'[/yellow]")
    console.print(f"[bold cyan]Model Choice:[/bold cyan] [yellow]'{exc.model_choice}'[/yellow]")
    console.print(f"\n[bold red]Error:[/bold red]        {exc.message}\n")
    console.print(
        f"[bold green]💡 Tip:[/bold green] Check your model configuration in [cyan].pipelex/inference/[/cyan] "
        f"or specify a different model in the [yellow]'{exc.pipe_code}'[/yellow] pipe."
    )
    console.print(f"[dim]Learn more about the inference backend system: {URLs.backend_provider_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_model_availability_error(exc: PipeOperatorModelAvailabilityError, context: ErrorContext) -> NoReturn:
    """Handle and display PipeOperatorModelAvailabilityError with formatted output.

    Args:
        exc: The model availability error exception
        context: Context for the error message
    """
    console = Console(stderr=True)
    console.print(f"\n[bold red]❌ {context} failed because a model wasn't available[/bold red]\n")
    console.print(f"[bold cyan]Pipe:[/bold cyan]         [yellow]'{exc.pipe_code}'[/yellow] [dim]({exc.pipe_type})[/dim]")
    console.print(f"[bold cyan]Model:[/bold cyan]        [yellow]'{exc.model_handle}'[/yellow]")
    if exc.fallback_list:
        fallbacks_str = ", ".join([f"[yellow]{fb}[/yellow]" for fb in exc.fallback_list])
        console.print(f"[bold cyan]Fallbacks:[/bold cyan]    {fallbacks_str}")
    if len(exc.pipe_stack) > 1:
        stack_str = " [dim]→[/dim] ".join([f"[yellow]{p}[/yellow]" for p in exc.pipe_stack])
        console.print(f"[bold cyan]Pipe Stack:[/bold cyan]   {stack_str}")
    console.print(f"\n[bold red]Error:[/bold red]        {exc}\n")
    console.print(
        f"[bold green]💡 Tip:[/bold green] Check your model configuration in [cyan].pipelex/inference/[/cyan] "
        f"or specify a different model in the [yellow]'{exc.pipe_code}'[/yellow] pipe."
    )
    console.print(f"[dim]Learn more about the inference backend system: {URLs.backend_provider_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_model_deck_preset_error(exc: ModelDeckPresetValidatonError, context: ErrorContext) -> NoReturn:
    """Handle and display ModelDeckPresetValidatonError with formatted output.

    Args:
        exc: The model deck preset validation error exception
        context: Context for the error message
    """
    console = Console(stderr=True)
    console.print(f"\n[bold red]❌ {context} failed due to model deck preset validation error[/bold red]\n")
    console.print(f"[bold cyan]Preset ID:[/bold cyan]    [yellow]'{exc.preset_id}'[/yellow]")
    console.print(f"[bold cyan]Model Type:[/bold cyan]   [yellow]'{exc.model_type}'[/yellow]")
    console.print(f"[bold cyan]Model Handle:[/bold cyan] [yellow]'{exc.model_handle}'[/yellow]")
    if exc.enabled_backends:
        backends_str = ", ".join([f"[yellow]{b}[/yellow]" for b in sorted(exc.enabled_backends)])
        console.print(f"[bold cyan]Enabled Backends:[/bold cyan] {backends_str}")
    console.print(f"\n[bold red]Error:[/bold red]        {exc.message}\n")
    backends_str = ", ".join([f"[yellow]{b}[/yellow]" for b in sorted(exc.enabled_backends)])
    console.print(
        f"[bold green]💡 Tip:[/bold green] The preset [yellow]'{exc.preset_id}'[/yellow] references model handle "
        f"[yellow]'{exc.model_handle}'[/yellow] which is not available in any enabled backend.\n"
        f"The enabled backends are: {backends_str}."
    )
    console.print(
        "[bold]Possible solutions:[/bold]\n"
        "  1. Update the preset to use a different model\n"
        f"  2. Configure model '{exc.model_handle}' in one of your enabled backends\n"
        f"  3. Enable a backend that supports [yellow]'{exc.model_handle}'[/yellow]"
    )
    console.print(f"\n[dim]Learn more about the inference backend system: {URLs.backend_provider_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_validation_error(exc: PipelexValidationExceptionAbstract, context: ErrorContext) -> NoReturn:
    """Handle and display validation errors with formatted output.

    Args:
        exc: The validation error exception (implements ValidationErrorDetailsProtocol)
        context: Context for the error message
    """
    console = Console(stderr=True)
    console.print(f"\n[bold red]❌ {context} failed due to validation error[/bold red]\n")
    console.print(f"[bold red]Error:[/bold red]        {exc}\n")

    # Display concept definition errors with syntax highlighting
    concept_definition_errors = exc.get_concept_definition_errors()
    if concept_definition_errors:
        console.print("[bold cyan]Concept Definition Errors:[/bold cyan]\n")
        for concept_definition_error in concept_definition_errors:
            syntax_error_data = concept_definition_error.structure_class_syntax_error_data
            if not syntax_error_data:
                continue

            message = concept_definition_error.message
            code = concept_definition_error.structure_class_python_code or ""
            highlight_lines: set[int] | None = None
            if syntax_error_data.lineno:
                highlight_lines = {syntax_error_data.lineno}

            syntax = Syntax(
                code=code,
                lexer="python",
                line_numbers=True,
                word_wrap=False,
                theme="ansi_dark",
                line_range=None,
                highlight_lines=highlight_lines,
            )

            # Build pretty error location
            pretty_range = ""
            if syntax_error_data.lineno and syntax_error_data.end_lineno:
                pretty_range = f"lines {syntax_error_data.lineno} to {syntax_error_data.end_lineno}"
            elif syntax_error_data.lineno:
                pretty_range = f"line {syntax_error_data.lineno}"
            if syntax_error_data.offset and syntax_error_data.end_offset:
                pretty_range += f", column {syntax_error_data.offset} to {syntax_error_data.end_offset}"
            elif syntax_error_data.offset:
                pretty_range += f", column {syntax_error_data.offset}"

            console.print(f"[yellow]{message}[/yellow]")
            if pretty_range:
                console.print(f"[dim]Generated code error at {pretty_range}[/dim]")
            console.print(syntax)
            console.print()

    console.print(
        "[bold green]💡 Tip:[/bold green] Review the error message above and check your pipeline configuration. "
        "Make sure all required fields are present and correctly formatted."
    )
    console.print(f"[dim]Learn more: {URLs.documentation}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc
