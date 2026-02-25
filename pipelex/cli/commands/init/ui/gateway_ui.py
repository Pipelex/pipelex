"""UI components for Pipelex Gateway terms acceptance flow."""

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text

from pipelex.urls import URLs


def build_gateway_terms_panel() -> Panel:
    """Build a Rich Panel explaining Pipelex Gateway terms and telemetry.

    Returns:
        A Panel containing the gateway terms explanation.
    """
    title_text = Text("Pipelex Gateway Terms of Service", style="bold yellow")

    intro = Text(
        "You have selected Pipelex Gateway as an inference backend.\nBy using Pipelex Gateway, you agree to the following terms:\n",
        style="white",
    )

    telemetry_header = Text("\n📊 Identified Telemetry Requirement\n", style="bold cyan")

    telemetry_explanation = Text(
        "When using Pipelex Gateway, identified telemetry is automatically enabled.\n"
        "Your usage is associated with your Gateway API key (hashed for security).\n\n"
        "This is independent from your telemetry.toml settings and allows us to:\n"
        "  • Monitor and improve service quality\n"
        "  • Enforce fair usage limits and prevent abuse\n"
        "  • Provide you with usage insights and better support\n\n"
        "We collect ONLY technical and quantitative data:\n",
        style="white",
    )

    collected_items = Text(
        "  ✓ Model names used (e.g., gpt-4o, claude-3.7-sonnet) and parameters\n"
        "  ✓ Pipe types (e.g., PipeLLM, PipeSequence, etc.)\n"
        "  ✓ Token counts (input/output)\n"
        "  ✓ Latency metrics\n"
        "  ✓ Error rates (without error details)\n",
        style="green",
    )

    not_collected = Text(
        "\nWe do NOT collect:\n",
        style="white",
    )

    not_collected_items = Text(
        "  ✗ Your prompts or completions\n  ✗ Your pipe codes or output class names\n  ✗ File contents or business data\n",
        style="red",
    )

    optional_note = Text(
        "\n💡 This is Optional\n",
        style="bold cyan",
    )

    optional_explanation = Text(
        "Using Pipelex Gateway is entirely optional. If you prefer not to use our gateway:\n"
        "  • Disable pipelex_gateway in your backends configuration in .pipelex/inference/backends.toml\n"
        "  • Use your own API keys with direct provider backends (openai, anthropic, azure, bedrock, etc.)\n"
        "  • No telemetry will be sent to Pipelex servers\n",
        style="white",
    )

    links = Text(
        f"\n📚 Documentation: {URLs.documentation}\n🔒 Privacy Policy: {URLs.privacy_policy}\n💬 Questions? Join Discord: {URLs.discord}\n",
        style="dim",
    )

    content = Group(
        intro,
        telemetry_header,
        telemetry_explanation,
        collected_items,
        not_collected,
        not_collected_items,
        optional_note,
        optional_explanation,
        links,
    )

    return Panel(
        content,
        title=title_text,
        border_style="yellow",
        padding=(1, 2),
    )


def prompt_gateway_acceptance(console: Console) -> bool:
    """Prompt the user to accept Pipelex Gateway terms.

    Args:
        console: Rich Console instance for user interaction.

    Returns:
        True if user accepts, False if declined.
    """
    console.print()
    console.print(build_gateway_terms_panel())
    console.print()

    return Confirm.ask(
        "[bold]Do you accept the Pipelex Gateway terms of service?[/bold]",
        console=console,
        default=True,
    )


def display_gateway_declined_message(console: Console) -> None:
    """Display message when user declines gateway terms.

    Args:
        console: Rich Console instance for output.
    """
    console.print()
    console.print("[yellow]⚠ Pipelex Gateway terms not accepted.[/yellow]")
    console.print()
    console.print("Pipelex Gateway has been disabled in your backends configuration.")
    console.print()
    console.print("[bold yellow]⚠ Important:[/bold yellow] If your routing profile uses pipelex_gateway as its default backend,")
    console.print("  you will need to reconfigure your routing profile.")
    console.print("  Run [cyan]pipelex init routing[/cyan] to select a different default backend.")
    console.print()
    console.print("[bold]Alternative options:[/bold]")
    console.print("  • Use your own API keys with direct provider backends")
    console.print("  • Available backends: openai, anthropic, google, bedrock, etc.")
    console.print()
    console.print(f"[dim]Need help? Visit {URLs.documentation} or join {URLs.discord}[/dim]")


def display_gateway_accepted_message(console: Console) -> None:
    """Display confirmation message when user accepts gateway terms.

    Args:
        console: Rich Console instance for output.
    """
    console.print()
    console.print("[green]✓ Pipelex Gateway terms accepted.[/green]")
    console.print("[dim]Identified telemetry (tied to your API key) will be enabled for service monitoring.[/dim]")
