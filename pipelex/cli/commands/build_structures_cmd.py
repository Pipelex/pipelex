from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from kajson.kajson_manager import KajsonManager

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import validate_bundles_from_directory
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.system.runtime import IntegrationMode

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint

COMMAND = "structures"


async def build_structures_cmd(
    target_directory: Annotated[
        str,
        typer.Argument(help="Target directory to scan for PLX files"),
    ],
    output_dir: Annotated[
        str | None,
        typer.Option("--output-dir", "-o", help="Output directory for generated structures (default: structures)"),
    ] = None,
) -> None:
    """Generate Python structure files from concept definitions in PLX files."""
    target_path = Path(target_directory).resolve()

    if not target_path.exists():
        typer.secho(f"❌ Target directory does not exist: {target_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if not target_path.is_dir():
        typer.secho(f"❌ Target path is not a directory: {target_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)

    try:
        output_directory = Path(output_dir) if output_dir else target_path / "structures"
        output_directory.mkdir(parents=True, exist_ok=True)

        typer.echo(f"🔍 Validating bundles in: {target_path}")

        # Validate bundles from directory
        validate_result = await validate_bundles_from_directory(directory=target_path)

        # Extract blueprints
        all_blueprints: list[PipelexBundleBlueprint] = validate_result.blueprints

        typer.echo(f"✅ Validated {len(all_blueprints)} blueprint(s)")

        # Reload class registry to detect manually-created structure classes
        # This ensures we don't regenerate classes that users have manually created
        class_registry = KajsonManager.get_class_registry()
        class_registry.teardown()
        class_registry.setup()
        ClassRegistryUtils.register_classes_in_folder(
            folder_path=str(target_path),
            base_class=StructuredContent,
            force_exclude_dirs=[str(output_directory.resolve())],
        )

        # Note: At this point, the registry contains manually-created classes from the library.
        # We'll check has_class() for each concept to skip regenerating manual classes.

        # Track generated files
        generated_files: list[tuple[str, str]] = []  # (domain, concept_code)

        for blueprint in all_blueprints:
            if blueprint.domain == "native":
                continue

            if not blueprint.concept:
                continue

            for concept_code, concept_blueprint in blueprint.concept.items():
                # Check if structure class was manually created (exists in registry after setup but before structures/)
                if class_registry.has_class(name=concept_code):
                    # Manually-created structure class exists, skip generation
                    existing_class = class_registry.get_class(name=concept_code)
                    if existing_class:
                        # Try to get the actual file location
                        import inspect  # noqa: PLC0415

                        try:
                            source_file = inspect.getfile(existing_class)
                            log.warning(
                                f"Skipping Generation for '{concept_code}' (domain '{blueprint.domain}'): "
                                f"manually-created class exists at '{source_file}'"
                            )
                        except (TypeError, OSError):
                            # Fallback if we can't get the file
                            module_name = existing_class.__module__ if hasattr(existing_class, "__module__") else "unknown"
                            log.warning(
                                f"Skipping '{concept_code}' (domain '{blueprint.domain}'): manually-created class exists in module '{module_name}'"
                            )
                    continue

                # Handle simple string concept definitions (description only, refines Text by default)
                if isinstance(concept_blueprint, str):
                    # String concept definition means: description=string, refines=Text
                    # Generate a class that inherits from TextContent
                    try:
                        generated_code, _ = StructureGenerator().generate_from_structure_blueprint(
                            class_name=concept_code,
                            structure_blueprint={},  # Empty structure - just inherits from TextContent
                            base_class_name="TextContent",
                        )
                    except ConceptStructureGeneratorError as exc:
                        msg = f"Error generating structure class for concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                        raise PipelexError(msg) from exc

                    # Write generated structure to file: domain_conceptCode.py
                    output_file = output_directory / f"{blueprint.domain}_{concept_code}.py"
                    output_file.write_text(generated_code)
                    generated_files.append((blueprint.domain, concept_code))
                    continue

                # Handle concepts with explicit structure definition
                if concept_blueprint.structure:
                    if isinstance(concept_blueprint.structure, str):
                        # Structure is defined as a string reference to existing class - skip generation
                        continue
                    # Structure is defined as a ConceptStructureBlueprint - run the structure generator
                    # Normalize the structure blueprint to ensure all values are ConceptStructureBlueprint objects
                    normalized_structure = ConceptFactory.normalize_structure_blueprint(concept_blueprint.structure)

                    try:
                        generated_code, _ = StructureGenerator().generate_from_structure_blueprint(
                            class_name=concept_code,
                            structure_blueprint=normalized_structure,
                        )
                    except ConceptStructureGeneratorError as exc:
                        msg = f"Error generating python code for structure class of concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                        raise PipelexError(
                            msg,
                        ) from exc

                    # Write generated structure to file: domain_conceptCode.py
                    output_file = output_directory / f"{blueprint.domain}_{concept_code}.py"
                    output_file.write_text(generated_code)
                    generated_files.append((blueprint.domain, concept_code))

                # Handle concepts with refines - generate a class that inherits from the refined structure
                elif concept_blueprint.refines:
                    try:
                        current_refine = ConceptFactory.make_refine(refine=concept_blueprint.refines)
                    except Exception as exc:
                        msg = (
                            f"Could not validate refine '{concept_blueprint.refines}' for concept '{concept_code}' "
                            f"in domain '{blueprint.domain}': {exc}"
                        )
                        raise PipelexError(msg) from exc

                    # Get the refined concept's structure class name
                    refined_structure_class_name = current_refine.split(".")[1] + "Content" if current_refine else "TextContent"

                    try:
                        generated_code, _ = StructureGenerator().generate_from_structure_blueprint(
                            class_name=concept_code,
                            structure_blueprint={},  # Empty structure - just inherits from refined class
                            base_class_name=refined_structure_class_name,
                        )
                    except ConceptStructureGeneratorError as exc:
                        msg = (
                            f"Error generating python code for structure class of concept '{concept_code}' "
                            f"refining '{refined_structure_class_name}' in domain '{blueprint.domain}': {exc}"
                        )
                        raise PipelexError(msg) from exc

                    # Write generated structure to file: domain_conceptCode.py
                    output_file = output_directory / f"{blueprint.domain}_{concept_code}.py"
                    output_file.write_text(generated_code)
                    generated_files.append((blueprint.domain, concept_code))

                # Handle concepts with neither structure nor refines - defaults to TextContent
                else:
                    # No structure or refines specified - generate a class that inherits from TextContent
                    try:
                        generated_code, _ = StructureGenerator().generate_from_structure_blueprint(
                            class_name=concept_code,
                            structure_blueprint={},  # Empty structure - just inherits from TextContent
                            base_class_name="TextContent",
                        )
                    except ConceptStructureGeneratorError as exc:
                        msg = f"Error generating structure class for concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                        raise PipelexError(msg) from exc

                    # Write generated structure to file: domain_conceptCode.py
                    output_file = output_directory / f"{blueprint.domain}_{concept_code}.py"
                    output_file.write_text(generated_code)
                    generated_files.append((blueprint.domain, concept_code))

        # Generate empty __init__.py to make structures importable
        if generated_files:
            init_file = output_directory / "__init__.py"
            init_file.write_text("")
            typer.echo(f"\n📝 Generated structures in: {output_directory}")
            typer.echo("  ✅ __init__.py")
            for domain_name, concept_code in generated_files:
                typer.echo(f"  ✅ {domain_name}_{concept_code}.py")

        typer.secho("\n✨ Done!", fg=typer.colors.GREEN)

    finally:
        pipelex_instance.teardown()
