"""Agent CLI assemble command - assemble TOML bundle from parts with JSON output."""

# pyright: reportUnknownMemberType=false
# pyright: reportArgumentType=false
# mypy: disable-error-code="arg-type"

from pathlib import Path
from typing import Annotated

import tomlkit
import typer

from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success


def _merge_toml_sections(
    base_doc: tomlkit.TOMLDocument,
    section_name: str,
    content_to_merge: tomlkit.TOMLDocument,
) -> None:
    """Merge a section from content into the base document.

    Args:
        base_doc: The base TOML document to merge into.
        section_name: The name of the section (e.g., "concept", "pipe").
        content_to_merge: The content document to merge (tomlkit preserves inline tables).
    """
    if section_name not in content_to_merge:
        return

    section_content = content_to_merge[section_name]
    if not section_content:
        return

    if section_name not in base_doc:
        base_doc.add(section_name, tomlkit.table())

    existing_section = base_doc[section_name]
    for key, value in section_content.items():  # type: ignore[union-attr]
        existing_section[key] = value  # type: ignore[index]


def _load_toml_content(source: str) -> tomlkit.TOMLDocument:
    """Load TOML content from either a file path or inline string.

    Uses tomlkit to preserve inline tables and formatting.

    Args:
        source: Either a file path or inline TOML string.

    Returns:
        Parsed TOML document that preserves formatting.
    """
    source_path = Path(source)
    if source_path.exists() and source_path.is_file():
        with open(source_path, encoding="utf-8") as the_file:
            return tomlkit.load(the_file)
    return tomlkit.parse(source)


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
        # Create base document with domain header
        doc = tomlkit.document()
        doc.add("domain", domain)

        if description:
            doc.add("description", description)

        if system_prompt:
            doc.add("system_prompt", system_prompt)

        doc.add("main_pipe", main_pipe)

        # Process concept sources
        if concepts:
            for concept_source in concepts:
                try:
                    concept_content = _load_toml_content(concept_source)
                    _merge_toml_sections(doc, "concept", concept_content)
                except FileNotFoundError as exc:
                    agent_error(f"Concept file not found: {concept_source}", "FileNotFoundError", cause=exc)
                except Exception as exc:
                    agent_error(f"Failed to load concepts from '{concept_source}': {exc}", "ConceptLoadError", cause=exc)

        # Process pipe sources
        if pipes:
            for pipe_source in pipes:
                try:
                    pipe_content = _load_toml_content(pipe_source)
                    _merge_toml_sections(doc, "pipe", pipe_content)
                except FileNotFoundError as exc:
                    agent_error(f"Pipe file not found: {pipe_source}", "FileNotFoundError", cause=exc)
                except Exception as exc:
                    agent_error(f"Failed to load pipes from '{pipe_source}': {exc}", "PipeLoadError", cause=exc)

        toml_content = tomlkit.dumps(doc)
        if not toml_content.endswith("\n"):
            toml_content += "\n"

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
