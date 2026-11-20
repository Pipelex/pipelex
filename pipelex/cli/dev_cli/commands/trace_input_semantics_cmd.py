"""Capture harness for the input-semantics audit: per-hop dumps of the input-schema emission chain.

Given one or more MTHDS bundle files, this tool loads them through the validation library and,
inside the validation window, dumps one artifact per hop of the chain that turns authored `.mthds`
facts into the `json_schema` emitted on `pipe_io_contracts`:

- ``hop1_bundle_blueprints.json`` — parse: the `PipelexBundleBlueprint` dumps (what survived TOML).
- ``hop2_structure_classes/`` — resolve + build: per traced concept, the structure class the loaded
  library holds for it, read off the class (name, bases, docstring, and each field's annotation,
  requiredness, whether it admits None, default, default factory's name and description): the class
  the runtime built from the concept's structure at load time, or the class a
  `structure = "ClassName"` concept names.
- ``hop2_python_structures.py.txt`` — the module the `python-structures` codegen emitter renders for
  the loaded crate, the file `pipelex build structures` would write. It agrees with the runtime's
  classes on concepts with a structure table only (see the codegen projections page).
- ``hop3_raw_pydantic_schemas/`` — raw `model_json_schema()` per concept's structure class,
  before any Pipelex render wrapping.
- ``hop4_schema_renders/`` — the `ConceptRepresentationFormat.SCHEMA` render per pipe input
  (the `{"concept": ..., "content": ...}` envelope, with array wrapping when multiple).
- ``hop5_pipe_io_contracts.json`` — the final wire contracts from `build_pipe_io_contracts`.
- ``hop5_input_form.json`` — the input-form descriptors from `build_input_form`, the projection
  that reads the authored facts directly (a fact lost on the schema side should survive here).
- ``trace_manifest.json`` — the capture inventory plus the wire framing per pipe input
  (authored ref string, resolved concept ref, multiplicity, presence marker).

The tool is a tracer, not a report generator: it never mutates the loaded library, and analysis
of the captures (e.g. a survival table) stays with the caller.
"""

import asyncio
import inspect
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from pydantic import BaseModel
from pydantic_core import to_jsonable_python
from rich.markup import escape

from pipelex.base_exceptions import PipelexError
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.stuffs.non_null_any import field_admits_none
from pipelex.interpreter_hub import (
    clear_current_library,
    get_concept_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.input_form import build_input_form
from pipelex.pipeline.pipe_io_contracts import build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.runtime_hub import get_console

MANIFEST_FILE_NAME = "trace_manifest.json"
HOP1_FILE_NAME = "hop1_bundle_blueprints.json"
HOP2_DIR_NAME = "hop2_structure_classes"
HOP2_PYTHON_STRUCTURES_FILE_NAME = "hop2_python_structures.py.txt"
HOP3_DIR_NAME = "hop3_raw_pydantic_schemas"
HOP4_DIR_NAME = "hop4_schema_renders"
HOP5_FILE_NAME = "hop5_pipe_io_contracts.json"
HOP5_INPUT_FORM_FILE_NAME = "hop5_input_form.json"


def _write_json(*, path: Path, payload: Any) -> None:
    _write_text(path=path, content=json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _write_text(*, path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _capture_hop1(*, blueprints: list[PipelexBundleBlueprint], output_dir: Path) -> str:
    payload = [blueprint.model_dump(mode="json") for blueprint in blueprints]
    _write_json(path=output_dir / HOP1_FILE_NAME, payload=payload)
    return HOP1_FILE_NAME


def _qualified_name_of(*, factory: Callable[..., Any]) -> str:
    """A default factory's dotted name, `module.qualname`, the same on every run.

    Not `repr`, which writes a function's memory address and so changes from one run to the next, and the captures are
    diffed across runs. Not what the factory returns either: calling it could have effects or give a different value each
    time (a timestamp, an id), and a factory may take the validated data as its argument. A callable without a name of its
    own, such as a `functools.partial`, is named by its type.
    """
    qualname: str | None = getattr(factory, "__qualname__", None)
    module: str | None = getattr(factory, "__module__", None)
    if qualname is None:
        qualname = type(factory).__qualname__
        module = type(factory).__module__
    return f"{module}.{qualname}"


def _structure_class_dump(*, structure_class: type[BaseModel]) -> dict[str, Any]:
    """What a structure class holds, read off the class itself: its name, bases, docstring and fields."""
    fields: dict[str, Any] = {}
    for field_name, field_info in structure_class.model_fields.items():
        fields[field_name] = {
            "annotation": repr(field_info.annotation),
            "required": field_info.is_required(),
            "admits_none": field_admits_none(field_info=field_info),
            # A required field's default, and that of a field with a default factory, is pydantic's `PydanticUndefined`
            # sentinel, which is written as its repr. The factory is named, never called.
            "default": to_jsonable_python(field_info.default, fallback=repr),
            "default_factory": _qualified_name_of(factory=field_info.default_factory) if field_info.default_factory is not None else None,
            "description": field_info.description,
        }
    return {
        "class_name": structure_class.__name__,
        "bases": [base_class.__name__ for base_class in structure_class.__bases__],
        # The docstring as pydantic writes it to the schema's description, so it reads as hop 3 does. Not
        # `inspect.getdoc`, which walks the MRO and gives `BaseModel`'s docstring to a class without its own.
        "doc": inspect.cleandoc(structure_class.__doc__) if structure_class.__doc__ else None,
        "fields": fields,
    }


def _capture_hop2(
    *,
    concept_refs: list[str],
    concept_provider: ConceptProviderAbstract,
    output_dir: Path,
) -> dict[str, str | None]:
    """Dump the structure class the runtime holds for each traced concept, as the loaded library resolves it.

    The class is the one the library registered: the class the runtime built from the concept's structure, or the
    class a `structure = "ClassName"` concept names. A concept that declares no structure class (`native.Anything`)
    maps to None.
    """
    captures: dict[str, str | None] = {}
    for concept_ref in concept_refs:
        concept = concept_provider.get_required_concept(concept_ref)
        if not concept.declares_a_structure_class:
            captures[concept_ref] = None
            continue
        structure_class = concept_provider.get_structure_class(concept=concept)
        relative_path = f"{HOP2_DIR_NAME}/{concept_ref}.json"
        _write_json(path=output_dir / relative_path, payload=_structure_class_dump(structure_class=structure_class))
        captures[concept_ref] = relative_path
    return captures


def _capture_hop2_python_structures(*, library_id: str | None, output_dir: Path) -> str | None:
    """Write the module the `python-structures` codegen emitter renders for the loaded library's crate.

    It is the file a user of `pipelex build structures` would get, with every class named as the runtime names it. For
    a concept with a structure table it has the JSON schema of the class the runtime builds; a structureless concept, a
    class-backed concept, a refinement of a concept outside the crate and a `native.Anything` field are rendered
    differently (see `docs/under-the-hood/codegen-projections.md`). None when the library holds no crate.
    """
    crate = get_library_manager().get_crate(library_id=library_id) if library_id is not None else None
    if crate is None:
        return None
    resolved_library = resolve_concepts_from_crate(normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)).with_qualified_names()
    [emitted_file] = emit_python_structures(resolved_library)
    # `.py.txt` on purpose: this is an evidence artifact, not code — a bare `.py` extension would drag it into the repo's
    # linters when the output directory is inside the repository.
    _write_text(path=output_dir / HOP2_PYTHON_STRUCTURES_FILE_NAME, content=emitted_file.content)
    return HOP2_PYTHON_STRUCTURES_FILE_NAME


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


def _capture_hop5_input_form(*, pipes: list[PipeAbstract], output_dir: Path) -> str:
    """The descriptor projection, captured beside the schema one so the two can be diffed fact by fact."""
    input_form = build_input_form(pipes)
    payload = {pipe_ref: descriptor.model_dump(mode="json") for pipe_ref, descriptor in input_form.items()}
    _write_json(path=output_dir / HOP5_INPUT_FORM_FILE_NAME, payload=payload)
    return HOP5_INPUT_FORM_FILE_NAME


def _build_wire_framing(*, blueprints: list[PipelexBundleBlueprint], pipes: list[PipeAbstract]) -> list[dict[str, Any]]:
    """One entry per pipe input: what the author wrote versus what the loaded spec resolved it to."""
    authored_specs: dict[str, str] = {}
    for blueprint in blueprints:
        if not blueprint.pipe:
            continue
        for pipe_code, pipe_blueprint in blueprint.pipe.items():
            if not pipe_blueprint.inputs:
                continue
            # The framing manifest tracks the slot grammar (ref + markers), so an expanded-form slot
            # contributes its `concept` string; its hints surface at hop 5 (the input-form descriptor).
            for var_name, authored in (pipe_blueprint.inputs_concept_specs or {}).items():
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
    # The per-item hop directories accumulate one file per concept / per pipe input, so a rerun
    # into the same output directory must replace them wholesale — a leftover capture from a
    # removed or renamed declaration would read as part of the current trace.
    for hop_dir_name in (HOP2_DIR_NAME, HOP3_DIR_NAME, HOP4_DIR_NAME):
        stale_hop_dir = output_dir / hop_dir_name
        if stale_hop_dir.is_dir():
            shutil.rmtree(stale_hop_dir)
    (output_dir / HOP2_PYTHON_STRUCTURES_FILE_NAME).unlink(missing_ok=True)

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
        concept_refs = _collect_traced_concept_refs(blueprints=result.blueprints, pipes=result.pipes)
        hop2_captures = _capture_hop2(concept_refs=concept_refs, concept_provider=concept_provider, output_dir=output_dir)
        hop2_python_structures_capture = _capture_hop2_python_structures(library_id=validation_library_id, output_dir=output_dir)
        hop3_captures, hop3_skipped = _capture_hop3(concept_refs=concept_refs, concept_provider=concept_provider, output_dir=output_dir)
        hop4_captures = _capture_hop4(pipes=result.pipes, concept_provider=concept_provider, output_dir=output_dir)
        hop5_capture = _capture_hop5(pipes=result.pipes, output_dir=output_dir)
        hop5_input_form_capture = _capture_hop5_input_form(pipes=result.pipes, output_dir=output_dir)
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
        "hop2_structure_classes": hop2_captures,
        "hop2_python_structures": hop2_python_structures_capture,
        "hop3_raw_pydantic_schemas": hop3_captures,
        "hop3_skipped": hop3_skipped,
        "hop4_schema_renders": hop4_captures,
        "hop5_pipe_io_contracts": hop5_capture,
        "hop5_input_form": hop5_input_form_capture,
        "wire_framing": wire_framing,
    }
    _write_json(path=output_dir / MANIFEST_FILE_NAME, payload=manifest)
    return manifest


def trace_input_semantics_cmd(*, bundle_paths: list[Path], output_dir: Path, allow_signatures: bool = False) -> None:
    """CLI wrapper: boot Pipelex, run the trace, report the artifact inventory."""
    console = get_console()
    for bundle_path in bundle_paths:
        if not bundle_path.is_file():
            console.print(f"[red]Bundle file not found: {escape(str(bundle_path))}[/red]")
            sys.exit(2)

    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False)
    try:
        manifest = asyncio.run(
            trace_input_semantics(
                bundle_paths=bundle_paths,
                output_dir=output_dir,
                allow_signatures=allow_signatures,
            )
        )
    except ValidateBundleError as exc:
        console.print(f"[red]Bundle validation failed — the trace requires a valid bundle:[/red]\n{escape(str(exc))}")
        sys.exit(1)
    except PipelexError as exc:
        console.print(f"[red]Trace failed:[/red]\n{escape(str(exc))}")
        sys.exit(1)
    finally:
        Pipelex.teardown_if_needed()

    console.print(f"[green]✓ Input-semantics trace written to {output_dir}[/green]")
    console.print(f"  hop 1: {manifest['hop1_bundle_blueprints']}")
    console.print(
        f"  hop 2: {len(manifest['hop2_structure_classes'])} structure classes under {HOP2_DIR_NAME}/ + {manifest['hop2_python_structures']}"
    )
    console.print(f"  hop 3: {len(manifest['hop3_raw_pydantic_schemas'])} raw schemas under {HOP3_DIR_NAME}/")
    console.print(f"  hop 4: {len(manifest['hop4_schema_renders'])} schema renders under {HOP4_DIR_NAME}/")
    console.print(f"  hop 5: {manifest['hop5_pipe_io_contracts']} + {manifest['hop5_input_form']}")
    console.print(f"  manifest: {MANIFEST_FILE_NAME}")
