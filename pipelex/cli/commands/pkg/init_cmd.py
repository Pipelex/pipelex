from pathlib import Path

import typer

from pipelex.core.packages.bundle_scanner import build_domain_exports_from_scan, scan_bundles_for_domain_info
from pipelex.core.packages.discovery import MANIFEST_FILENAME
from pipelex.core.packages.manifest import MthdsPackageManifest
from pipelex.core.packages.manifest_parser import serialize_manifest_to_toml
from pipelex.hub import get_console


def do_pkg_init(force: bool = False) -> None:
    """Scan .mthds files in the current directory and generate a METHODS.toml skeleton.

    Args:
        force: If True, overwrite an existing METHODS.toml
    """
    console = get_console()
    cwd = Path.cwd()
    manifest_path = cwd / MANIFEST_FILENAME

    # Check if manifest already exists
    if manifest_path.exists() and not force:
        console.print(f"[red]METHODS.toml already exists at {manifest_path}[/red]")
        console.print("Use --force to overwrite.")
        raise typer.Exit(code=1)

    # Scan for .mthds files
    mthds_files = sorted(cwd.rglob("*.mthds"))
    if not mthds_files:
        console.print("[red]No .mthds files found in the current directory.[/red]")
        raise typer.Exit(code=1)

    # Parse each bundle header to extract domain and main_pipe
    domain_pipes, domain_main_pipes, errors = scan_bundles_for_domain_info(mthds_files)

    if errors:
        console.print("[yellow]Some files could not be parsed:[/yellow]")
        for error in errors:
            console.print(f"  {error}")

    # Build exports from collected domain/pipe data, placing main_pipe first
    exports = build_domain_exports_from_scan(domain_pipes, domain_main_pipes)

    # Generate manifest with placeholder address
    dir_name = cwd.name.replace("-", "_").replace(" ", "_").lower()
    manifest = MthdsPackageManifest(
        address=f"example.com/yourorg/{dir_name}",
        version="0.1.0",
        description=f"Package generated from {len(mthds_files)} .mthds file(s)",
        exports=exports,
    )

    # Serialize and write
    toml_content = serialize_manifest_to_toml(manifest)
    manifest_path.write_text(toml_content, encoding="utf-8")

    console.print(f"[green]Created {MANIFEST_FILENAME}[/green] with:")
    console.print(f"  Domains: {len(domain_pipes)}")
    console.print(f"  Total pipes: {sum(len(pipes) for pipes in domain_pipes.values())}")
    console.print(f"  Bundles scanned: {len(mthds_files)}")
    console.print(f"\n[dim]Edit {MANIFEST_FILENAME} to set the correct address and configure exports.[/dim]")
