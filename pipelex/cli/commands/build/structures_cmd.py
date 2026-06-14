import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.helpers import (
    get_structure_class_name_from_blueprint,
    make_qualified_structure_class_name,
    normalize_structure_blueprint,
)
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import ConceptClassInfo, StructureGenerator
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.registry_models import CoreRegistryModels
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry, get_func_registry, resolve_library_dirs
from pipelex.pipeline.validate_bundle import load_concepts_only, load_concepts_only_from_directory
from pipelex.tools.misc.string_utils import pascal_case_to_snake_case

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint

SUB_COMMAND_STRUCTURES = "structures"


def _compute_relative_path_from_output_dir(output_directory: Path) -> Path | None:
    """Compute the relative path from the output directory to the current working directory.

    Args:
        output_directory: The directory where structure files will be generated

    Returns:
        Relative path or None if cannot be determined
    """
    try:
        cwd = Path.cwd()
        return output_directory.resolve().relative_to(cwd)
    except ValueError:
        return None


def _build_concept_ref_to_class_info(
    blueprints: list["PipelexBundleBlueprint"],
    *,
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
    base_relative_path = _compute_relative_path_from_output_dir(output_directory)

    for blueprint in blueprints:
        if blueprint.domain == "native":
            continue

        if not blueprint.concept:
            continue

        for concept_code, concept_blueprint in blueprint.concept.items():
            # Build the concept ref (domain.ConceptCode)
            concept_ref = f"{blueprint.domain}.{concept_code}"

            # Get the class name from the blueprint. When the helper returns the bare
            # concept_code (i.e. no user-supplied structure class reference), qualify
            # it with the domain so cross-class imports/types match the qualified
            # class definitions emitted below.
            raw_class_name = get_structure_class_name_from_blueprint(concept_blueprint, concept_ref_or_code=concept_code)
            if raw_class_name == concept_code:
                class_name = make_qualified_structure_class_name(domain_code=blueprint.domain, concept_code=concept_code)
                file_stem_snake_case = pascal_case_to_snake_case(concept_code)
            else:
                class_name = raw_class_name
                file_stem_snake_case = pascal_case_to_snake_case(raw_class_name)

            # Build the module path for this concept's structure file
            if base_relative_path:
                base_module_path = ".".join(base_relative_path.parts)
                module_path = f"{base_module_path}.{blueprint.domain}__{file_stem_snake_case}"
            else:
                module_path = None

            concept_ref_to_class_info[concept_ref] = ConceptClassInfo(
                class_name=class_name,
                module_path=module_path,
            )

    return concept_ref_to_class_info


def generate_structures_from_blueprints(
    blueprints: list["PipelexBundleBlueprint"],
    *,
    output_directory: Path,
    target_path: Path | None = None,
    skip_existing_check: bool = False,
    quiet: bool = False,
) -> list[tuple[str, str]]:
    """Generate Python structure files from blueprint concept definitions.

    Args:
        blueprints: List of PipelexBundleBlueprint containing concept definitions
        output_directory: Directory where structure files will be generated
        target_path: Optional path to scan for manually-created structure classes
        skip_existing_check: If True, always generate structures without checking if they exist
        quiet: If True, suppress progress output (use log.verbose instead of typer.echo/secho)

    Returns:
        List of (domain, concept_code) tuples for generated files
    """
    output_directory.mkdir(parents=True, exist_ok=True)

    # Build concept_ref_to_class_info mapping for all concepts
    concept_ref_to_class_info = _build_concept_ref_to_class_info(blueprints, output_directory=output_directory)
    class_registry = get_class_registry()

    # Only check for existing classes if we're not skipping and have a target path
    check_existing = not skip_existing_check and target_path is not None

    generated_files: list[tuple[str, str]] = []

    if quiet:
        log.verbose(f"Generating structures in: {output_directory}")
    else:
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
                    generated_code, _ = StructureGenerator(
                        concept_ref_to_class_info=concept_ref_to_class_info, local_domain=blueprint.domain
                    ).generate_from_structure_blueprint(
                        class_name=make_qualified_structure_class_name(domain_code=blueprint.domain, concept_code=concept_code),
                        structure_blueprint={},
                        base_class_name=TextContent.__name__,
                        description=concept_blueprint,
                    )
                except ConceptStructureGeneratorError as exc:
                    msg = f"Error generating structure class for concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                    raise PipelexError(msg) from exc

                concept_snake_case = pascal_case_to_snake_case(concept_code)
                output_file = output_directory / f"{blueprint.domain}__{concept_snake_case}.py"
                output_file.write_text(generated_code)
                generated_files.append((blueprint.domain, concept_code))
                if not quiet:
                    typer.secho(f"  ✅ Generated {output_file.name}", fg=typer.colors.GREEN)
                else:
                    log.verbose(f"Generated {output_file.name}")
                continue

            # Handle concepts with explicit structure definition
            if concept_blueprint.structure:
                if isinstance(concept_blueprint.structure, str):
                    continue
                normalized_structure = normalize_structure_blueprint(concept_blueprint.structure)

                try:
                    generated_code, the_generated_class = StructureGenerator(
                        concept_ref_to_class_info=concept_ref_to_class_info,
                        local_domain=blueprint.domain,
                    ).generate_from_structure_blueprint(
                        class_name=make_qualified_structure_class_name(domain_code=blueprint.domain, concept_code=concept_code),
                        structure_blueprint=normalized_structure,
                        description=concept_blueprint.description,
                    )
                except ConceptStructureGeneratorError as exc:
                    msg = f"Error generating python code for structure class of concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                    raise PipelexError(msg) from exc

                # Register the generated class so it can be used as a base class for refined concepts
                get_class_registry().register_class(the_generated_class)

                concept_snake_case = pascal_case_to_snake_case(concept_code)
                output_file = output_directory / f"{blueprint.domain}__{concept_snake_case}.py"
                output_file.write_text(generated_code)
                generated_files.append((blueprint.domain, concept_code))
                if not quiet:
                    typer.secho(f"  ✅ Generated {output_file.name}", fg=typer.colors.GREEN)
                else:
                    log.verbose(f"Generated {output_file.name}")

            # Handle concepts with refines
            elif concept_blueprint.refines:
                current_refine = ConceptFactory.make_refine(refine=concept_blueprint.refines, domain_code=blueprint.domain)

                # For native concepts, the structure class name is "ConceptCode" + "Content" (e.g., TextContent)
                # For custom concepts, the structure class name is the domain-qualified name
                # (e.g., other_domain__Customer) so it matches what ConceptFactory registers.
                if current_refine:
                    refined_ref = QualifiedRef.parse_stripping_cross_package(current_refine)
                    refined_concept_code = refined_ref.local_code
                    if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=current_refine):
                        refined_structure_class_name = refined_concept_code + "Content"
                    else:
                        refined_domain_code = refined_ref.domain_path or blueprint.domain
                        refined_structure_class_name = make_qualified_structure_class_name(
                            domain_code=refined_domain_code, concept_code=refined_concept_code
                        )
                else:
                    refined_structure_class_name = TextContent.__name__

                try:
                    generated_code, the_generated_class = StructureGenerator(
                        concept_ref_to_class_info=concept_ref_to_class_info,
                        local_domain=blueprint.domain,
                    ).generate_from_structure_blueprint(
                        class_name=make_qualified_structure_class_name(domain_code=blueprint.domain, concept_code=concept_code),
                        structure_blueprint={},
                        base_class_name=refined_structure_class_name,
                        description=concept_blueprint.description,
                    )
                except ConceptStructureGeneratorError as exc:
                    msg = (
                        f"Error generating python code for structure class of concept '{concept_code}' "
                        f"refining '{refined_structure_class_name}' in domain '{blueprint.domain}': {exc}"
                    )
                    raise PipelexError(msg) from exc

                # Register the generated class so it can be used as a base class for other refined concepts
                get_class_registry().register_class(the_generated_class)

                concept_snake_case = pascal_case_to_snake_case(concept_code)
                output_file = output_directory / f"{blueprint.domain}__{concept_snake_case}.py"
                output_file.write_text(generated_code)
                generated_files.append((blueprint.domain, concept_code))
                if not quiet:
                    typer.secho(f"  ✅ Generated {output_file.name}", fg=typer.colors.GREEN)
                else:
                    log.verbose(f"Generated {output_file.name}")

            # Handle concepts with neither structure nor refines - defaults to TextContent
            else:
                try:
                    generated_code, the_generated_class = StructureGenerator(
                        concept_ref_to_class_info=concept_ref_to_class_info,
                        local_domain=blueprint.domain,
                    ).generate_from_structure_blueprint(
                        class_name=make_qualified_structure_class_name(domain_code=blueprint.domain, concept_code=concept_code),
                        structure_blueprint={},
                        base_class_name=TextContent.__name__,
                        description=concept_blueprint.description,
                    )
                except ConceptStructureGeneratorError as exc:
                    msg = f"Error generating structure class for concept '{concept_code}' in domain '{blueprint.domain}': {exc}"
                    raise PipelexError(msg) from exc

                # Register the generated class so it can be used as a base class for refined concepts
                get_class_registry().register_class(the_generated_class)

                concept_snake_case = pascal_case_to_snake_case(concept_code)
                output_file = output_directory / f"{blueprint.domain}__{concept_snake_case}.py"
                output_file.write_text(generated_code)
                generated_files.append((blueprint.domain, concept_code))
                if not quiet:
                    typer.secho(f"  ✅ Generated {output_file.name}", fg=typer.colors.GREEN)
                else:
                    log.verbose(f"Generated {output_file.name}")

    # Generate empty __init__.py to make structures importable
    if generated_files:
        init_file = output_directory / "__init__.py"
        init_file.write_text("")
        if not quiet:
            typer.secho("  ✅ Generated __init__.py", fg=typer.colors.GREEN)
        else:
            log.verbose("Generated __init__.py")

    return generated_files


def build_structures_command(
    target: Annotated[
        str,
        typer.Argument(help="Target directory to scan for .mthds files, or a specific .mthds file"),
    ],
    output_dir: Annotated[
        str | None,
        typer.Option("--output-dir", "-o", help="Output directory for generated structures (default: structures/ in target's directory)"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force regeneration of all structures, overwriting existing files without checking if classes already exist.",
        ),
    ] = False,
) -> None:
    """Generate Python structure classes from concept definitions in .mthds files.

    Examples:
        pipelex build structures my_bundle.mthds
        pipelex build structures ./my_pipes/
        pipelex build structures my_bundle.mthds -o ./generated/
        pipelex build structures my_bundle.mthds -L ./shared_pipes/
        pipelex build structures my_bundle.mthds --force
    """

    def _build_structures_cmd():
        target_path = Path(target).resolve()

        if not target_path.exists():
            typer.secho(f"❌ Target does not exist: {target_path}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

        # Resolve library directories using the standard 3-tier priority
        library_dirs_paths, _ = resolve_library_dirs(library_dir)

        # Determine if target is a file or directory
        is_mthds_file = target_path.is_file() and is_pipelex_file(target_path)
        pipelex_instance = make_pipelex_for_cli(context=ErrorContext.BUILD, library_dirs=library_dir, needs_inference=False)

        try:
            if is_mthds_file:
                # Single MTHDS file: output to parent directory
                base_dir = target_path.parent
                output_directory = Path(output_dir) if output_dir else base_dir / "structures"

                typer.echo(f"🔍 Loading concepts from bundle: {target_path}")

                # Load concepts only (no pipes)
                load_result = load_concepts_only(mthds_file_path=target_path, library_dirs=library_dirs_paths)
                # THIS IS A HACK, while waiting class/func registries to be in libraries.
                get_class_registry().teardown()
                get_func_registry().teardown()
                get_class_registry().register_classes(CoreRegistryModels.get_all_models())

                all_blueprints: list[PipelexBundleBlueprint] = load_result.blueprints

                typer.echo(f"✅ Loaded {len(all_blueprints)} blueprint(s)")

                # Generate structures using the helper function
                generated_files = generate_structures_from_blueprints(
                    blueprints=all_blueprints,
                    output_directory=output_directory,
                    target_path=base_dir,
                    skip_existing_check=force,
                )
            else:
                # Directory: scan for all MTHDS files
                if not target_path.is_dir():
                    typer.secho(f"❌ Target is not a directory or .mthds file: {target_path}", fg=typer.colors.RED, err=True)
                    raise typer.Exit(1)

                output_directory = Path(output_dir) if output_dir else target_path / "structures"

                typer.echo(f"🔍 Loading concepts from bundles in: {target_path}")

                # Load concepts only from directory (no pipes)
                load_result = load_concepts_only_from_directory(directory=target_path)
                # THIS IS A HACK, while waiting class/func registries to be in libraries.
                get_class_registry().teardown()
                get_func_registry().teardown()
                get_class_registry().register_classes(CoreRegistryModels.get_all_models())

                typer.echo(f"✅ Loaded {len(load_result.blueprints)} blueprint(s)")

                # Generate structures using the helper function
                generated_files = generate_structures_from_blueprints(
                    blueprints=load_result.blueprints,
                    output_directory=output_directory,
                    target_path=target_path,
                    skip_existing_check=force,
                )

            if generated_files:
                typer.secho(f"\n✨ Done! Generated {len(generated_files)} structure(s) in: {output_directory}", fg=typer.colors.GREEN)
            else:
                typer.secho("\n✨ Done! No structures to generate.", fg=typer.colors.GREEN)

        finally:
            pipelex_instance.teardown()

    _build_structures_cmd()
