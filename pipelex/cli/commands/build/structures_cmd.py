import asyncio
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from kajson.kajson_manager import KajsonManager

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.helpers import get_structure_class_name_from_blueprint, normalize_structure_blueprint
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import ConceptClassInfo, StructureGenerator
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.validate_bundle import validate_bundle, validate_bundles_from_directory
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.tools.misc.string_utils import pascal_case_to_snake_case

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint

SUB_COMMAND_STRUCTURES = "structures"


def _compute_module_path_from_output_dir(output_directory: Path) -> str | None:
    """Compute the Python module path from the output directory.

    Args:
        output_directory: The directory where structure files will be generated

    Returns:
        Module path string (e.g., "pipeline_01.structures") or None if cannot be determined
    """
    try:
        # Get relative path from current working directory
        cwd = Path.cwd()
        rel_path = output_directory.resolve().relative_to(cwd)
        # Convert path to module path (replace / with .)
        return str(rel_path).replace("/", ".").replace("\\", ".")
    except ValueError:
        # output_directory is not relative to cwd
        return None


def _build_concept_ref_to_class_info(
    blueprints: list["PipelexBundleBlueprint"],
    output_directory: Path,
) -> dict[str, ConceptClassInfo]:
    """Build a mapping from concept refs to their class info including module paths.

    Args:
        blueprints: List of PipelexBundleBlueprint containing concept definitions
        output_directory: Directory where structure files will be generated

    Returns:
        Mapping from concept_ref to ConceptClassInfo with module paths
    """
    concept_ref_to_class_info: dict[str, ConceptClassInfo] = {}
    base_module_path = _compute_module_path_from_output_dir(output_directory)

    for blueprint in blueprints:
        if blueprint.domain == "native":
            continue

        if not blueprint.concept:
            continue

        for concept_code, concept_blueprint in blueprint.concept.items():
            # Build the concept ref (domain.ConceptCode)
            concept_ref = f"{blueprint.domain}.{concept_code}"

            # Get the class name from the blueprint
            class_name = get_structure_class_name_from_blueprint(concept_blueprint, concept_code)

            # Build the module path for this concept's structure file
            class_name_snake_case = pascal_case_to_snake_case(class_name)
            if base_module_path:
                module_path = f"{base_module_path}.{blueprint.domain}__{class_name_snake_case}"
            else:
                module_path = None

            concept_ref_to_class_info[concept_ref] = ConceptClassInfo(
                class_name=class_name,
                module_path=module_path,
            )

    return concept_ref_to_class_info


def generate_structures_from_blueprints(
    blueprints: list["PipelexBundleBlueprint"],
    output_directory: Path,
    target_path: Path | None = None,
    skip_existing_check: bool = False,
) -> list[tuple[str, str]]:
    """Generate Python structure files from blueprint concept definitions.

    Args:
        blueprints: List of PipelexBundleBlueprint containing concept definitions
        output_directory: Directory where structure files will be generated
        target_path: Optional path to scan for manually-created structure classes
        skip_existing_check: If True, always generate structures without checking if they exist

    Returns:
        List of (domain, concept_code) tuples for generated files
    """
    output_directory.mkdir(parents=True, exist_ok=True)

    # Build concept_ref_to_class_info mapping for all concepts
    concept_ref_to_class_info = _build_concept_ref_to_class_info(blueprints, output_directory)

    # Only check for existing classes if we're not skipping and have a target path
    check_existing = not skip_existing_check and target_path is not None
    class_registry = KajsonManager.get_class_registry()
    if check_existing:
        class_registry.teardown()
        class_registry.setup()
        ClassRegistryUtils.register_classes_in_folder(
            folder_path=str(target_path),
            base_class=StructuredContent,
            force_exclude_dirs=[str(output_directory.resolve())],
        )

    generated_files: list[tuple[str, str]] = []

    typer.echo(f"\n📝 Generating structures in: {output_directory}")

    for blueprint in blueprints:
        if blueprint.domain == "native":
            continue

        if not blueprint.concept:
            continue

        for concept_code, concept_blueprint in blueprint.concept.items():
            # Check if structure class was manually created (only when check_existing is enabled)
            if check_existing and class_registry.has_class(name=concept_code):
                existing_class = class_registry.get_class(name=concept_code)
                if existing_class:
                    try:
                        source_file = inspect.getfile(existing_class)
                        log.warning(
                            f"Skipping Generation for '{concept_code}' (domain '{blueprint.domain}'): "
                            f"manually-created class exists at '{source_file}'"
                        )
                    except (TypeError, OSError):
                        module_name = existing_class.__module__ if hasattr(existing_class, "__module__") else "unknown"
                        log.warning(
                            f"Skipping '{concept_code}' (domain '{blueprint.domain}'): manually-created class exists in module '{module_name}'"
                        )
                continue

            # Handle simple string concept definitions (description only, refines Text by default)
            if isinstance(concept_blueprint, str):
                try:
                    generated_code, _ = StructureGenerator(concept_ref_to_class_info=concept_ref_to_class_info).generate_from_structure_blueprint(
                        class_name=concept_code,
                        structure_blueprint={},
                        base_class_name=TextContent.__name__,
                    )
                except ConceptStructureGeneratorError as exc:
                    msg = f"Error generating structure class for concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                    raise PipelexError(msg) from exc

                concept_snake_case = pascal_case_to_snake_case(concept_code)
                output_file = output_directory / f"{blueprint.domain}__{concept_snake_case}.py"
                output_file.write_text(generated_code)
                generated_files.append((blueprint.domain, concept_code))
                typer.secho(f"  ✅ Generated {output_file.name}", fg=typer.colors.GREEN)
                continue

            # Handle concepts with explicit structure definition
            if concept_blueprint.structure:
                if isinstance(concept_blueprint.structure, str):
                    continue
                normalized_structure = normalize_structure_blueprint(concept_blueprint.structure)

                try:
                    generated_code, _ = StructureGenerator(concept_ref_to_class_info=concept_ref_to_class_info).generate_from_structure_blueprint(
                        class_name=concept_code,
                        structure_blueprint=normalized_structure,
                    )
                except ConceptStructureGeneratorError as exc:
                    msg = f"Error generating python code for structure class of concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                    raise PipelexError(msg) from exc

                concept_snake_case = pascal_case_to_snake_case(concept_code)
                output_file = output_directory / f"{blueprint.domain}__{concept_snake_case}.py"
                output_file.write_text(generated_code)
                generated_files.append((blueprint.domain, concept_code))
                typer.secho(f"  ✅ Generated {output_file.name}", fg=typer.colors.GREEN)

            # Handle concepts with refines
            elif concept_blueprint.refines:
                try:
                    current_refine = ConceptFactory.make_refine(refine=concept_blueprint.refines, domain_code=blueprint.domain)
                except Exception as exc:
                    msg = (
                        f"Could not validate refine '{concept_blueprint.refines}' for concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                    )
                    raise PipelexError(msg) from exc

                refined_structure_class_name = current_refine.split(".")[1] + "Content" if current_refine else TextContent.__name__

                try:
                    generated_code, _ = StructureGenerator(concept_ref_to_class_info=concept_ref_to_class_info).generate_from_structure_blueprint(
                        class_name=concept_code,
                        structure_blueprint={},
                        base_class_name=refined_structure_class_name,
                    )
                except ConceptStructureGeneratorError as exc:
                    msg = (
                        f"Error generating python code for structure class of concept '{concept_code}' "
                        f"refining '{refined_structure_class_name}' in domain '{blueprint.domain}': {exc}"
                    )
                    raise PipelexError(msg) from exc

                concept_snake_case = pascal_case_to_snake_case(concept_code)
                output_file = output_directory / f"{blueprint.domain}__{concept_snake_case}.py"
                output_file.write_text(generated_code)
                generated_files.append((blueprint.domain, concept_code))
                typer.secho(f"  ✅ Generated {output_file.name}", fg=typer.colors.GREEN)

            # Handle concepts with neither structure nor refines - defaults to TextContent
            else:
                try:
                    generated_code, _ = StructureGenerator(concept_ref_to_class_info=concept_ref_to_class_info).generate_from_structure_blueprint(
                        class_name=concept_code,
                        structure_blueprint={},
                        base_class_name=TextContent.__name__,
                    )
                except ConceptStructureGeneratorError as exc:
                    msg = f"Error generating structure class for concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                    raise PipelexError(msg) from exc

                concept_snake_case = pascal_case_to_snake_case(concept_code)
                output_file = output_directory / f"{blueprint.domain}__{concept_snake_case}.py"
                output_file.write_text(generated_code)
                generated_files.append((blueprint.domain, concept_code))
                typer.secho(f"  ✅ Generated {output_file.name}", fg=typer.colors.GREEN)

    # Generate empty __init__.py to make structures importable
    if generated_files:
        init_file = output_directory / "__init__.py"
        init_file.write_text("")
        typer.secho("  ✅ Generated __init__.py", fg=typer.colors.GREEN)

    return generated_files


def build_structures_command(
    target: Annotated[
        str,
        typer.Argument(help="Target directory to scan for PLX files, or a specific .plx file"),
    ],
    output_dir: Annotated[
        str | None,
        typer.Option("--output-dir", "-o", help="Output directory for generated structures (default: structures/ in target's directory)"),
    ] = None,
) -> None:
    """Generate Python structure files from concept definitions in PLX files."""

    async def _build_structures_cmd():
        target_path = Path(target).resolve()

        if not target_path.exists():
            typer.secho(f"❌ Target does not exist: {target_path}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

        # Determine if target is a file or directory
        is_plx_file = target_path.is_file() and target_path.suffix == ".plx"

        pipelex_instance = make_pipelex_for_cli(context=ErrorContext.BUILD)

        try:
            if is_plx_file:
                # Single PLX file: output to parent directory
                base_dir = target_path.parent
                output_directory = Path(output_dir) if output_dir else base_dir / "structures"

                typer.echo(f"🔍 Validating bundle: {target_path}")

                # Validate single bundle
                validate_result = await validate_bundle(plx_file_path=str(target_path))
                all_blueprints: list[PipelexBundleBlueprint] = validate_result.blueprints

                typer.echo(f"✅ Validated {len(all_blueprints)} blueprint(s)")

                # Generate structures using the helper function
                generated_files = generate_structures_from_blueprints(
                    blueprints=all_blueprints,
                    output_directory=output_directory,
                    target_path=base_dir,
                )
            else:
                # Directory: scan for all PLX files
                if not target_path.is_dir():
                    typer.secho(f"❌ Target is not a directory or .plx file: {target_path}", fg=typer.colors.RED, err=True)
                    raise typer.Exit(1)

                output_directory = Path(output_dir) if output_dir else target_path / "structures"

                typer.echo(f"🔍 Validating bundles in: {target_path}")

                # Validate bundles from directory
                validate_result = await validate_bundles_from_directory(directory=target_path)
                all_blueprints = validate_result.blueprints

                typer.echo(f"✅ Validated {len(all_blueprints)} blueprint(s)")

                # Generate structures using the helper function
                generated_files = generate_structures_from_blueprints(
                    blueprints=all_blueprints,
                    output_directory=output_directory,
                    target_path=target_path,
                )

            if generated_files:
                typer.secho(f"\n✨ Done! Generated {len(generated_files)} structure(s) in: {output_directory}", fg=typer.colors.GREEN)
            else:
                typer.secho("\n✨ Done! No structures to generate.", fg=typer.colors.GREEN)

        finally:
            pipelex_instance.teardown()

    asyncio.run(_build_structures_cmd())
