from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.libraries.library_utils import get_pipelex_plx_files_from_dirs
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
    from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint

COMMAND = "structures"


def build_structures_cmd(
    target_directory: Annotated[
        str,
        typer.Argument(help="Target directory to scan for PLX files"),
    ],
    output_dir: Annotated[
        str | None,
        typer.Option("--output-dir", "-o", help="Output directory for generated structures (default: .structures)"),
    ] = None,
) -> None:
    """Generate Python structure files from concept definitions in PLX files.

    This command scans a target directory for PLX files, extracts all concepts
    with structure definitions, and generates corresponding Python files in the
    .structures directory.

    Examples:
        pipelex build structures .
        pipelex build structures ./my_pipelines
        pipelex build structures ./my_pipelines --output-dir ./generated_structures
    """
    target_path = Path(target_directory).resolve()

    if not target_path.exists():
        typer.secho(f"❌ Target directory does not exist: {target_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if not target_path.is_dir():
        typer.secho(f"❌ Target path is not a directory: {target_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # Initialize Pipelex (required for library utilities)
    pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)

    try:
        # Determine output directory
        output_directory = Path(output_dir) if output_dir else target_path / ".structures"
        output_directory.mkdir(parents=True, exist_ok=True)

        typer.echo(f"🔍 Scanning for PLX files in: {target_path}")

        # Discover all PLX files in the target directory
        plx_files = get_pipelex_plx_files_from_dirs({target_path})

        if not plx_files:
            typer.secho(f"⚠️  No PLX files found in {target_path}", fg=typer.colors.YELLOW)
            raise typer.Exit(0)

        typer.echo(f"📁 Found {len(plx_files)} PLX file(s)")

        # Process each PLX file
        all_blueprints: list[PipelexBundleBlueprint] = []
        concept_structures: dict[str, tuple[str, dict[str, ConceptStructureBlueprint]]] = {}

        for plx_file in plx_files:
            typer.echo(f"📄 Processing: {plx_file.relative_to(target_path) if plx_file.is_relative_to(target_path) else plx_file}")

            try:
                # Parse the PLX file
                blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=str(plx_file))
                all_blueprints.append(blueprint)

                # Extract concepts with structure definitions
                if blueprint.concept:
                    for concept_code, concept_blueprint_or_description in blueprint.concept.items():
                        # Skip string descriptions (they don't have structure definitions)
                        if isinstance(concept_blueprint_or_description, str):
                            continue

                        concept_blueprint = concept_blueprint_or_description

                        # Only process concepts with dict-based structure definitions
                        if concept_blueprint.structure and isinstance(concept_blueprint.structure, dict):
                            # Normalize the structure blueprint
                            normalized_structure = ConceptFactory.normalize_structure_blueprint(concept_blueprint.structure)

                            # Store for generation (use domain.concept_code as key to avoid collisions)
                            full_concept_code = f"{blueprint.domain}.{concept_code}"
                            concept_structures[full_concept_code] = (concept_code, normalized_structure)
                            log.verbose(f"Found concept with structure: {full_concept_code}")

            except Exception as exc:
                typer.secho(f"⚠️  Failed to process {plx_file}: {exc}", fg=typer.colors.YELLOW, err=True)
                log.warning(f"Error processing PLX file {plx_file}: {exc}")
                continue

        if not concept_structures:
            typer.secho("⚠️  No concepts with structure definitions found", fg=typer.colors.YELLOW)
            typer.echo("💡 Tip: Concepts need structure definitions (dict form) to generate Python files")
            raise typer.Exit(0)

        typer.echo(f"\n🏗️  Generating structure files for {len(concept_structures)} concept(s)...")

        # Generate Python files for each concept
        generated_count = 0
        failed_count = 0

        for full_concept_code, (concept_code, structure_blueprint) in concept_structures.items():
            try:
                # Generate the Python code using StructureGenerator
                generator = StructureGenerator()
                generated_code, _ = generator.generate_from_structure_blueprint(
                    class_name=concept_code,
                    structure_blueprint=structure_blueprint,
                )

                # Write to file
                output_file = output_directory / f"{full_concept_code}.py"
                ensure_directory_for_file_path(str(output_file))

                Path(output_file).write_text(generated_code, encoding="utf-8")

                relative_path = output_file.relative_to(target_path) if output_file.is_relative_to(target_path) else output_file
                typer.echo(f"  ✅ {full_concept_code} -> {relative_path}")
                generated_count += 1

            except ConceptStructureGeneratorError as exc:
                typer.secho(f"  ❌ Failed to generate {full_concept_code}: {exc}", fg=typer.colors.RED, err=True)
                log.error(f"Failed to generate structure for {full_concept_code}: {exc}")
                failed_count += 1
            except Exception as exc:
                typer.secho(f"  ❌ Unexpected error generating {full_concept_code}: {exc}", fg=typer.colors.RED, err=True)
                log.error(f"Unexpected error generating structure for {full_concept_code}: {exc}")
                failed_count += 1

        # Summary
        typer.echo("\n📊 Summary:")
        typer.echo(f"  • PLX files processed: {len(plx_files)}")
        typer.echo(f"  • Concepts found: {len(concept_structures)}")
        typer.echo(f"  • Files generated: {generated_count}")
        if failed_count > 0:
            typer.secho(f"  • Failed: {failed_count}", fg=typer.colors.RED)
        typer.echo(f"  • Output directory: {output_directory}")

        if failed_count > 0:
            raise typer.Exit(1)

        typer.secho("\n✨ Structure generation complete!", fg=typer.colors.GREEN)

    finally:
        pipelex_instance.teardown()
