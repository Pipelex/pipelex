"""Agent CLI assemble command - assemble TOML bundle from parts with JSON output."""

# pyright: reportUnknownMemberType=false
# pyright: reportArgumentType=false
# mypy: disable-error-code="arg-type"

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import tomlkit
import typer


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
    """Assemble a complete .plx bundle from individual TOML parts.

    Combines domain configuration, concepts, and pipes into a single valid
    Pipelex bundle file. Each --concepts and --pipes argument can be either
    a file path or inline TOML content.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent assemble --domain my_domain --main-pipe main
            --concepts concepts.toml --pipes pipes.toml --output bundle.plx

        pipelex-agent assemble --domain my_domain --main-pipe main
            --concepts '[concept.MyInput]' --pipes '[pipe.main]'
            --output bundle.plx
    """
    error_json: dict[str, Any]

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
                except FileNotFoundError:
                    error_json = {
                        "error": True,
                        "error_type": "FileNotFoundError",
                        "message": f"Concept file not found: {concept_source}",
                    }
                    print(json.dumps(error_json, indent=2), file=sys.stderr)
                    raise typer.Exit(1) from None
                except Exception as exc:
                    error_json = {
                        "error": True,
                        "error_type": "ConceptLoadError",
                        "message": f"Failed to load concepts from '{concept_source}': {exc}",
                    }
                    print(json.dumps(error_json, indent=2), file=sys.stderr)
                    raise typer.Exit(1) from exc

        # Process pipe sources
        if pipes:
            for pipe_source in pipes:
                try:
                    pipe_content = _load_toml_content(pipe_source)
                    _merge_toml_sections(doc, "pipe", pipe_content)
                except FileNotFoundError:
                    error_json = {
                        "error": True,
                        "error_type": "FileNotFoundError",
                        "message": f"Pipe file not found: {pipe_source}",
                    }
                    print(json.dumps(error_json, indent=2), file=sys.stderr)
                    raise typer.Exit(1) from None
                except Exception as exc:
                    error_json = {
                        "error": True,
                        "error_type": "PipeLoadError",
                        "message": f"Failed to load pipes from '{pipe_source}': {exc}",
                    }
                    print(json.dumps(error_json, indent=2), file=sys.stderr)
                    raise typer.Exit(1) from exc

        # Write output file
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as out_file:
            tomlkit.dump(doc, out_file)

        # Ensure file ends with newline (POSIX standard)
        with open(output_path, "a", encoding="utf-8") as out_file:
            out_file.write("\n")

        result = {
            "success": True,
            "bundle_path": str(output_path.resolve()),
            "domain": domain,
            "main_pipe": main_pipe,
        }
        print(json.dumps(result, indent=2))

    except typer.Exit:
        raise

    except Exception as exc:
        error_json = {
            "error": True,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        print(json.dumps(error_json, indent=2), file=sys.stderr)
        raise typer.Exit(1) from exc
