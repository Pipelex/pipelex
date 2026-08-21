"""Capture harness for the input-semantics audit: per-hop dumps of the input-schema emission chain.

Given one or more MTHDS bundle files, this tool loads them through the validation library and,
inside the validation window, dumps one artifact per hop of the chain that turns authored `.mthds`
facts into the `json_schema` emitted on `pipe_io_contracts`:

- ``hop1_bundle_blueprints.json`` — parse: the `PipelexBundleBlueprint` dumps (what survived TOML).
- ``hop2_generated_sources/`` — resolve + generate: the structure-class source the runtime
  generates per concept, re-derived with the same `StructureGenerator` calls
  `ConceptFactory.make_from_blueprint` issues at load time.
- ``hop3_raw_pydantic_schemas/`` — raw `model_json_schema()` per concept's structure class,
  before any Pipelex render wrapping.
- ``hop4_schema_renders/`` — the `ConceptRepresentationFormat.SCHEMA` render per pipe input
  (the `{"concept": ..., "content": ...}` envelope, with array wrapping when multiple).
- ``hop5_pipe_io_contracts.json`` — the final wire contracts from `build_pipe_io_contracts`.
- ``trace_manifest.json`` — the capture inventory plus the wire framing per pipe input
  (authored ref string, resolved concept ref, multiplicity, presence marker).

The tool is a tracer, not a report generator: it never mutates the loaded library, and analysis
of the captures (e.g. a survival table) stays with the caller.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from pipelex.base_exceptions import PipelexError
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.helpers import make_qualified_structure_class_name, normalize_structure_blueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import (
    clear_current_library,
    get_concept_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.pipe_io_contracts import build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.runtime_hub import get_console

MANIFEST_FILE_NAME = "trace_manifest.json"
HOP1_FILE_NAME = "hop1_bundle_blueprints.json"
HOP2_DIR_NAME = "hop2_generated_sources"
HOP3_DIR_NAME = "hop3_raw_pydantic_schemas"
HOP4_DIR_NAME = "hop4_schema_renders"
HOP5_FILE_NAME = "hop5_pipe_io_contracts.json"


def _write_json(*, path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def regenerate_structure_source(
    *,
    domain_code: str,
    concept_code: str,
    declaration: ConceptBlueprint | str,
) -> str | None:
    """Re-derive the structure-class source the runtime generated for one concept declaration.

    Mirrors the generation branches of `ConceptFactory.make_from_blueprint`
    (pipelex/core/concepts/concept_factory.py) with the same `StructureGenerator` arguments, so the
    captured source is what the factory produced at load time. Returns None for a
    `structure = "ClassName"` declaration (the factory generates nothing there — the class
    pre-exists in the registry). Must run inside the validation window: generated code that
    inherits a bundle-defined base class resolves it through the class registry.
    """
    qualified_class_name = make_qualified_structure_class_name(domain_code=domain_code, concept_code=concept_code)

    if isinstance(declaration, str):
        source, _ = StructureGenerator().generate_from_structure_blueprint(
            class_name=qualified_class_name,
            structure_blueprint={},
            base_class_name=TextContent.__name__,
            description=declaration,
        )
        return source

    if isinstance(declaration.structure, str):
        return None

    if isinstance(declaration.structure, dict):
        normalized_structure = normalize_structure_blueprint(declaration.structure)
        source, _ = StructureGenerator(local_domain=domain_code).generate_from_structure_blueprint(
            class_name=qualified_class_name,
            structure_blueprint=normalized_structure,
            description=declaration.description,
        )
        return source

    if declaration.refines is not None:
        current_refine = ConceptFactory.make_refine(refine=declaration.refines, domain_code=domain_code)
        if QualifiedRef.has_cross_package_prefix(current_refine):
            source, _ = StructureGenerator().generate_from_structure_blueprint(
                class_name=qualified_class_name,
                structure_blueprint={},
                description=declaration.description,
            )
            return source
        refined_ref = QualifiedRef.parse(current_refine)
        refined_concept_code = refined_ref.local_code
        if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=current_refine):
            refined_structure_class_name = refined_concept_code + "Content"
        else:
            refined_domain_code = refined_ref.domain_path or domain_code
            refined_structure_class_name = make_qualified_structure_class_name(domain_code=refined_domain_code, concept_code=refined_concept_code)
        source, _ = StructureGenerator().generate_from_structure_blueprint(
            class_name=qualified_class_name,
            structure_blueprint={},
            base_class_name=refined_structure_class_name,
            description=declaration.description,
        )
        return source

    # Basic blueprint (description only): the factory generates an empty TextContent subclass.
    source, _ = StructureGenerator().generate_from_structure_blueprint(
        class_name=qualified_class_name,
        structure_blueprint={},
        base_class_name=TextContent.__name__,
        description=declaration.description,
    )
    return source


def _capture_hop1(*, blueprints: list[PipelexBundleBlueprint], output_dir: Path) -> str:
    payload = [blueprint.model_dump(mode="json") for blueprint in blueprints]
    _write_json(path=output_dir / HOP1_FILE_NAME, payload=payload)
    return HOP1_FILE_NAME


def _capture_hop2(*, blueprints: list[PipelexBundleBlueprint], output_dir: Path) -> dict[str, str | None]:
    captures: dict[str, str | None] = {}
    for blueprint in blueprints:
        if not blueprint.concept:
            continue
        for concept_code, declaration in blueprint.concept.items():
            concept_ref = f"{blueprint.domain}.{concept_code}"
            source = regenerate_structure_source(domain_code=blueprint.domain, concept_code=concept_code, declaration=declaration)
            if source is None:
                captures[concept_ref] = None
                continue
            # `.py.txt` on purpose: these are evidence artifacts, not code — a bare `.py`
            # extension would drag them into the repo's linters when captured under wip/.
            relative_path = f"{HOP2_DIR_NAME}/{concept_ref}.py.txt"
            source_path = output_dir / relative_path
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(source, encoding="utf-8")
            captures[concept_ref] = relative_path
    return captures


def _collect_traced_concept_refs(*, blueprints: list[PipelexBundleBlueprint], pipes: list[PipeAbstract]) -> list[str]:
    """Every concept the trace must render: bundle-declared concepts plus every pipe-input concept."""
    concept_refs: list[str] = []
    for blueprint in blueprints:
        if not blueprint.concept:
            continue
        for concept_code in blueprint.concept:
            concept_refs.append(f"{blueprint.domain}.{concept_code}")
    for pipe in pipes:
        for stuff_spec in pipe.inputs.root.values():
            concept_refs.append(stuff_spec.concept.concept_ref)
    # Preserve first-seen order while deduplicating.
    return list(dict.fromkeys(concept_refs))


def _capture_hop3(
    *,
    concept_refs: list[str],
    concept_provider: ConceptProviderAbstract,
    output_dir: Path,
) -> tuple[dict[str, str], list[str]]:
    captures: dict[str, str] = {}
    skipped: list[str] = []
    for concept_ref in concept_refs:
        concept = concept_provider.get_required_concept(concept_ref)
        if not concept.declares_a_structure_class:
            skipped.append(f"{concept_ref}: declares no structure class")
            continue
        structure_class = concept_provider.get_structure_class(concept=concept)
        relative_path = f"{HOP3_DIR_NAME}/{concept_ref}.json"
        _write_json(path=output_dir / relative_path, payload=structure_class.model_json_schema())
        captures[concept_ref] = relative_path
    return captures, skipped


def _capture_hop4(
    *,
    pipes: list[PipeAbstract],
    concept_provider: ConceptProviderAbstract,
    output_dir: Path,
) -> dict[str, str]:
    captures: dict[str, str] = {}
    for pipe in pipes:
        for var_name, stuff_spec in pipe.inputs.root.items():
            render = stuff_spec.render_stuff_spec(concept_provider=concept_provider, output_format=ConceptRepresentationFormat.SCHEMA)
            relative_path = f"{HOP4_DIR_NAME}/{pipe.pipe_ref}__{var_name}.json"
            _write_json(path=output_dir / relative_path, payload=render)
            captures[f"{pipe.pipe_ref}.{var_name}"] = relative_path
    return captures


def _capture_hop5(*, pipes: list[PipeAbstract], output_dir: Path) -> str:
    io_contracts = build_pipe_io_contracts(pipes)
    payload = {pipe_ref: contract.model_dump(mode="json") for pipe_ref, contract in io_contracts.items()}
    _write_json(path=output_dir / HOP5_FILE_NAME, payload=payload)
    return HOP5_FILE_NAME


def _build_wire_framing(*, blueprints: list[PipelexBundleBlueprint], pipes: list[PipeAbstract]) -> list[dict[str, Any]]:
    """One entry per pipe input: what the author wrote versus what the loaded spec resolved it to."""
    authored_specs: dict[str, str] = {}
    for blueprint in blueprints:
        if not blueprint.pipe:
            continue
        for pipe_code, pipe_blueprint in blueprint.pipe.items():
            if not pipe_blueprint.inputs:
                continue
            for var_name, authored in pipe_blueprint.inputs.items():
                authored_specs[f"{blueprint.domain}.{pipe_code}.{var_name}"] = authored

    framing: list[dict[str, Any]] = []
    for pipe in pipes:
        for var_name, stuff_spec in pipe.inputs.root.items():
            framing.append(
                {
                    "pipe_ref": pipe.pipe_ref,
                    "input_name": var_name,
                    "authored_spec": authored_specs.get(f"{pipe.pipe_ref}.{var_name}"),
                    "concept_ref": stuff_spec.concept.concept_ref,
                    "multiplicity": stuff_spec.multiplicity,
                    "presence": stuff_spec.presence,
                    "is_multiple": stuff_spec.is_multiple(),
                }
            )
    return framing


async def trace_input_semantics(
    *,
    bundle_paths: list[Path],
    output_dir: Path,
    allow_signatures: bool = False,
) -> dict[str, Any]:
    """Validate the given bundles and dump one artifact per hop of the input-schema chain.

    Runs `validate_bundle` and performs every capture inside the validation window (the schema
    renders resolve bundle-defined structure classes through the loaded library), then restores
    the caller's current library and tears the validation library down.

    Args:
        bundle_paths: The `.mthds` files to load as one bundle batch.
        output_dir: Directory receiving the per-hop artifacts (created if missing).
        allow_signatures: Tolerate unimplemented pipe signatures, as `validate_bundle` does.

    Returns:
        The manifest dict, also written to ``trace_manifest.json`` in ``output_dir``.

    Raises:
        ValidateBundleError: When the bundle is invalid — the trace requires a valid bundle.
    """
    mthds_contents = [bundle_path.read_text(encoding="utf-8") for bundle_path in bundle_paths]
    mthds_sources = [str(bundle_path) for bundle_path in bundle_paths]

    output_dir.mkdir(parents=True, exist_ok=True)

    prev_library_id = get_current_library_id_or_none()
    validation_library_id: str | None = None
    try:
        result = await validate_bundle(
            mthds_contents=mthds_contents,
            mthds_sources=mthds_sources,
            allow_signatures=allow_signatures,
        )
        validation_library_id = get_current_library_id_or_none()
        concept_provider = get_concept_library()

        hop1_capture = _capture_hop1(blueprints=result.blueprints, output_dir=output_dir)
        hop2_captures = _capture_hop2(blueprints=result.blueprints, output_dir=output_dir)
        concept_refs = _collect_traced_concept_refs(blueprints=result.blueprints, pipes=result.pipes)
        hop3_captures, hop3_skipped = _capture_hop3(concept_refs=concept_refs, concept_provider=concept_provider, output_dir=output_dir)
        hop4_captures = _capture_hop4(pipes=result.pipes, concept_provider=concept_provider, output_dir=output_dir)
        hop5_capture = _capture_hop5(pipes=result.pipes, output_dir=output_dir)
        wire_framing = _build_wire_framing(blueprints=result.blueprints, pipes=result.pipes)
    finally:
        if validation_library_id is not None and validation_library_id != prev_library_id:
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            get_library_manager().teardown(library_id=validation_library_id)

    manifest: dict[str, Any] = {
        "bundle_paths": mthds_sources,
        "hop1_bundle_blueprints": hop1_capture,
        "hop2_generated_sources": hop2_captures,
        "hop3_raw_pydantic_schemas": hop3_captures,
        "hop3_skipped": hop3_skipped,
        "hop4_schema_renders": hop4_captures,
        "hop5_pipe_io_contracts": hop5_capture,
        "wire_framing": wire_framing,
    }
    _write_json(path=output_dir / MANIFEST_FILE_NAME, payload=manifest)
    return manifest


def trace_input_semantics_cmd(*, bundle_paths: list[Path], output_dir: Path, allow_signatures: bool = False) -> None:
    """CLI wrapper: boot Pipelex, run the trace, report the artifact inventory."""
    console = get_console()
    for bundle_path in bundle_paths:
        if not bundle_path.is_file():
            console.print(f"[red]Bundle file not found: {bundle_path}[/red]")
            sys.exit(2)

    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False, needs_model_specs=True)
    try:
        manifest = asyncio.run(
            trace_input_semantics(
                bundle_paths=bundle_paths,
                output_dir=output_dir,
                allow_signatures=allow_signatures,
            )
        )
    except ValidateBundleError as exc:
        console.print(f"[red]Bundle validation failed — the trace requires a valid bundle:[/red]\n{exc}")
        sys.exit(1)
    except PipelexError as exc:
        console.print(f"[red]Trace failed:[/red]\n{exc}")
        sys.exit(1)
    finally:
        Pipelex.teardown_if_needed()

    console.print(f"[green]✓ Input-semantics trace written to {output_dir}[/green]")
    console.print(f"  hop 1: {manifest['hop1_bundle_blueprints']}")
    console.print(f"  hop 2: {len(manifest['hop2_generated_sources'])} generated sources under {HOP2_DIR_NAME}/")
    console.print(f"  hop 3: {len(manifest['hop3_raw_pydantic_schemas'])} raw schemas under {HOP3_DIR_NAME}/")
    console.print(f"  hop 4: {len(manifest['hop4_schema_renders'])} schema renders under {HOP4_DIR_NAME}/")
    console.print(f"  hop 5: {manifest['hop5_pipe_io_contracts']}")
    console.print(f"  manifest: {MANIFEST_FILE_NAME}")
