"""Helper functions for handling and displaying CLI errors."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

import typer
from rich.console import Console

from pipelex.urls import URLs

if TYPE_CHECKING:
    from pipelex.exceptions import PipeOperatorModelAvailabilityError, PipeOperatorModelChoiceError


class ErrorContext(StrEnum):
    """Context for error messages in CLI commands."""

    PIPE_RUN = "Pipe run"
    VALIDATION = "Pipe validation"
    BUILD = "Pipe build"


def handle_model_choice_error(exc: PipeOperatorModelChoiceError, context: ErrorContext) -> None:
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


def handle_model_availability_error(exc: PipeOperatorModelAvailabilityError, context: ErrorContext) -> None:
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
