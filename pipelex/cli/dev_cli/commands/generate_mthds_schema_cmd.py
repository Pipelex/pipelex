"""Command to generate JSON Schema for .mthds files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.panel import Panel

from pipelex.hub import get_console
from pipelex.language.mthds_schema_generator import generate_mthds_schema

# Path to the generated schema file, in the derived/ directory (gitignored)
MTHDS_SCHEMA_PATH = Path("derived/mthds_schema.json")


def generate_mthds_schema_cmd(output: Path | None = None, quiet: bool = False) -> None:
    """Generate a Taplo-compatible JSON Schema for .mthds files.

    Generates the schema from PipelexBundleBlueprint and writes it as JSON.
    The schema enables IDE validation and autocompletion in the vscode-pipelex extension.

    Args:
        output: Custom output path. Defaults to derived/mthds_schema.json.
        quiet: If True, output only a single validation line.
    """
    console = get_console()
    output_path = output or MTHDS_SCHEMA_PATH

    if not quiet:
        console.print()
        console.print("[bold]Generating MTHDS JSON Schema...[/bold]")
        console.print()

    try:
        schema = generate_mthds_schema()
    except Exception:  # noqa: BLE001
        # Dev CLI command root: any schema-generation failure is reported as a FAILED status line; exit non-zero.
        if quiet:
            console.print("[red]\u2717 MTHDS schema generation: FAILED[/red]")
        else:
            console.print("[bold red]\u2717 Failed to generate MTHDS schema[/bold red]")
        sys.exit(1)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the schema file
    schema_json = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    output_path.write_text(schema_json, encoding="utf-8")

    # Count definitions for reporting
    definition_count = len(schema.get("definitions", {}))

    if quiet:
        console.print(f"[green]\u2713 MTHDS schema generation: PASSED[/green] ({definition_count} definitions)")
    else:
        success_panel = Panel(
            f"[green]\u2713[/green] Schema generated successfully!\n\n[dim]Output: {output_path}[/dim]\n[dim]Definitions: {definition_count}[/dim]",
            title="[bold green]MTHDS Schema Generation: PASSED[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
        console.print(success_panel)
        console.print()
