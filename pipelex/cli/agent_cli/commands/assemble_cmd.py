"""Agent CLI assemble command - assemble TOML bundle from parts with JSON output."""

from pathlib import Path
from typing import Annotated

import typer

from pipelex.builder.operations.assemble_ops import assemble_bundle
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success


def assemble_cmd(
    domain: Annotated[
        str,
        typer.Option("--domain", "-d", help="Domain code for the bundle (snake_case)"),
    ],
    main_pipe: Annotated[
        str,
        typer.Option("--main-pipe", "-m", help="Main pipe code for the bundle"),
    ],
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Output file path (.mthds). Omit to return TOML in JSON response."),
    ] = None,
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
    """Assemble a complete .mthds bundle from individual TOML parts.

    Combines domain configuration, concepts, and pipes into a single valid
    Pipelex bundle file. Each --concepts and --pipes argument can be either
    a file path or inline TOML content.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent assemble --domain my_domain --main-pipe main
            --concepts concepts.toml --pipes pipes.toml

        pipelex-agent assemble --domain my_domain --main-pipe main
            --concepts concepts.toml --pipes pipes.toml --output bundle.mthds
    """
    try:
        toml_content = assemble_bundle(
            domain=domain,
            main_pipe=main_pipe,
            description=description,
            system_prompt=system_prompt,
            concept_tomls=concepts,
            pipe_tomls=pipes,
        )

        if output is None:
            # Stdout mode (default): return TOML in JSON response
            agent_success(
                {
                    "success": True,
                    "toml": toml_content,
                    "domain": domain,
                    "main_pipe": main_pipe,
                }
            )
        else:
            # File mode: write to disk
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(toml_content, encoding="utf-8")
            agent_success(
                {
                    "success": True,
                    "bundle_path": str(output_path.resolve()),
                    "domain": domain,
                    "main_pipe": main_pipe,
                }
            )

    except typer.Exit:
        raise

    except Exception as exc:
        agent_error(str(exc), type(exc).__name__, cause=exc)
