"""Main entry point for the agent CLI."""

from typing import Annotated

import typer
from click import Command, Context
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.agent_cli.commands.assemble_cmd import assemble_cmd
from pipelex.cli.agent_cli.commands.build_cmd import build_cmd
from pipelex.cli.agent_cli.commands.concept_cmd import concept_cmd
from pipelex.cli.agent_cli.commands.graph_cmd import GraphFormat, graph_cmd
from pipelex.cli.agent_cli.commands.inputs_cmd import inputs_cmd
from pipelex.cli.agent_cli.commands.pipe_cmd import pipe_cmd
from pipelex.cli.agent_cli.commands.run_cmd import run_cmd
from pipelex.cli.agent_cli.commands.validate_cmd import validate_cmd
from pipelex.cli.commands.doctor_cmd import doctor_cmd
from pipelex.tools.misc.package_utils import get_package_version


class PipelexAgentCLI(TyperGroup):
    """Custom Typer group for pipelex-agent CLI."""

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        """List commands in proper order."""
        return ["build", "run", "validate", "inputs", "concept", "pipe", "assemble", "graph", "doctor"]

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        """Get command by name."""
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(f"Unknown command: {cmd_name}")
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexAgentCLI,
)


def version_callback(value: bool) -> None:
    """Print version and exit when --version is passed."""
    if value:
        package_version = get_package_version()
        typer.echo(f"pipelex-agent {package_version}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def app_callback(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Agent CLI callback - no logo, minimal output."""
    # No logo, no banner - agent CLI is silent by default


@app.command(name="build", help="Build a pipeline from a prompt")
def build_command(
    prompt: Annotated[
        str,
        typer.Argument(help="Prompt describing what the pipeline should do"),
    ],
    builder_pipe: Annotated[
        str,
        typer.Option("--builder-pipe", help="Builder pipe to use for generating the pipeline"),
    ] = "pipe_builder",
) -> None:
    """Build a pipeline from a prompt and output JSON with paths."""
    build_cmd(prompt=prompt, builder_pipe=builder_pipe)


@app.command(name="run", help="Execute a pipeline and output JSON results")
def run_command(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to run"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.plx)"),
    ] = None,
    inputs: Annotated[
        str | None,
        typer.Option("--inputs", "-i", help="Path to JSON file with inputs or inline JSON"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run pipeline in dry mode (no actual inference calls)"),
    ] = False,
    mock_inputs: Annotated[
        bool,
        typer.Option("--mock-inputs", help="Generate mock data for missing required inputs (requires --dry-run)"),
    ] = False,
    graph: Annotated[
        bool,
        typer.Option("--graph", help="Generate execution graph visualizations (saved alongside output)"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.plx files)"),
    ] = None,
) -> None:
    """Execute a pipeline and output JSON results."""
    run_cmd(
        target=target,
        pipe=pipe,
        bundle=bundle,
        inputs=inputs,
        dry_run=dry_run,
        mock_inputs=mock_inputs,
        graph=graph,
        library_dir=library_dir,
    )


@app.command(name="validate", help="Validate a pipe, bundle, or all pipes and output JSON results")
def validate_command(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to validate"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.plx)"),
    ] = None,
    validate_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Validate all pipes in all libraries"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.plx files)"),
    ] = None,
) -> None:
    """Validate a pipe, bundle, or all pipes and output JSON results."""
    validate_cmd(
        target=target,
        pipe=pipe,
        bundle=bundle,
        validate_all=validate_all,
        library_dir=library_dir,
    )


@app.command(name="inputs", help="Generate example input JSON for a pipe")
def inputs_command(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to get inputs for"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.plx files)"),
    ] = None,
) -> None:
    """Generate example input JSON for a pipe."""
    inputs_cmd(
        target=target,
        pipe=pipe,
        library_dir=library_dir,
    )


@app.command(name="concept", help="Structure a concept from JSON spec and output TOML")
def concept_command(
    spec: Annotated[
        str | None,
        typer.Option("--spec", "-s", help="JSON string with concept specification"),
    ] = None,
    spec_file: Annotated[
        str | None,
        typer.Option("--spec-file", "-f", help="Path to JSON file with concept specification"),
    ] = None,
) -> None:
    """Structure a concept from JSON spec and output TOML."""
    concept_cmd(spec=spec, spec_file=spec_file)


@app.command(name="pipe", help="Structure a pipe from JSON spec and output TOML")
def pipe_command(
    pipe_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Pipe type (e.g., PipeLLM, PipeSequence)"),
    ],
    spec: Annotated[
        str | None,
        typer.Option("--spec", "-s", help="JSON string with pipe specification"),
    ] = None,
    spec_file: Annotated[
        str | None,
        typer.Option("--spec-file", "-f", help="Path to JSON file with pipe specification"),
    ] = None,
) -> None:
    """Structure a pipe from JSON spec and output TOML."""
    pipe_cmd(pipe_type=pipe_type, spec=spec, spec_file=spec_file)


@app.command(name="assemble", help="Assemble a complete .plx bundle from TOML parts")
def assemble_command(
    domain: Annotated[
        str,
        typer.Option("--domain", "-d", help="Domain code for the bundle (snake_case)"),
    ],
    main_pipe: Annotated[
        str,
        typer.Option("--main-pipe", "-m", help="Main pipe code for the bundle"),
    ],
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output file path for the assembled bundle (.plx)"),
    ],
    description: Annotated[
        str | None,
        typer.Option("--description", help="Description of the bundle"),
    ] = None,
    system_prompt: Annotated[
        str | None,
        typer.Option("--system-prompt", help="Default system prompt for LLM pipes"),
    ] = None,
    concepts: Annotated[
        list[str] | None,
        typer.Option("--concepts", "-c", help="TOML file(s) or inline TOML containing concept definitions"),
    ] = None,
    pipes: Annotated[
        list[str] | None,
        typer.Option("--pipes", "-p", help="TOML file(s) or inline TOML containing pipe definitions"),
    ] = None,
) -> None:
    """Assemble a complete .plx bundle from individual TOML parts."""
    assemble_cmd(
        domain=domain,
        main_pipe=main_pipe,
        output=output,
        description=description,
        system_prompt=system_prompt,
        concepts=concepts,
        pipes=pipes,
    )


@app.command(name="graph", help="Render a graphspec.json to HTML visualizations")
def graph_command(
    graphspec_file: Annotated[
        str,
        typer.Argument(help="Path to a graphspec.json file"),
    ],
    out: Annotated[
        str | None,
        typer.Option("--out", "-o", help="Output directory (default: same directory as input file)"),
    ] = None,
    graph_format: Annotated[
        GraphFormat,
        typer.Option("--format", "-f", help="Graph format to generate: mermaidflow, reactflow, or both"),
    ] = GraphFormat.BOTH,
) -> None:
    """Render a graphspec.json file to HTML visualizations."""
    graph_cmd(graphspec_file=graphspec_file, out=out, graph_format=graph_format)


@app.command(name="doctor", help="Check Pipelex configuration health and auto-fix issues")
def doctor_command() -> None:
    """Check Pipelex configuration health with auto-fix enabled."""
    doctor_cmd(fix=True)
