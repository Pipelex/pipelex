"""Generate the shared projection fixture corpus the two inputs-template projections are pinned against.

The corpus is committed byte-identically in `mthds-js/tests/fixtures/protocol/` and
`mthds-python/tests/fixtures/protocol/`, beside the descriptor capture already there. It pairs each
pipe's input-form descriptor with the fill-in template both projections must produce from it — the
compact and explicit shapes, as JSON and as TOML — so "equivalent between JS and Python" is a
measured property rather than an aspiration.

What this command writes into the output directory:

- ``input_form.json`` / ``pipe_io_contracts.json`` — the descriptor and contract capture, byte for
  byte what ``trace-input-semantics`` dumps at hop 5. This command is the sole producer of the
  committed copies; the tracer stays a debugging tool.
- ``inputs_template/<pipe_ref>.<shape>.<format>`` — the expected template, from the reference
  projection in ``projection_reference.py``.
- ``inputs_template/manifest.json`` — the pipes covered and the declared divergences from the
  engine's own renderer, each with worked examples a consumer repo can check with no engine present.
- ``engine/`` — the engine's own renderings, for review at capture time. **Not committed**: it is
  what the divergence record is measured against, not part of the contract.

The divergences are declared here, not discovered: a class that stops occurring fails this command
rather than quietly disappearing, so an engine fix retires its entry deliberately.
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from pipelex.base_exceptions import PipelexError
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.dev_cli.commands.projection_reference import (
    project_concept_comments,
    project_inputs_template,
)
from pipelex.cli.error_handlers import ErrorContext
from pipelex.interpreter_hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.rendering.input_renderer import (
    build_inputs_template,
    render_inputs,
    render_inputs_toml,
    serialize_inputs_template_to_toml,
)
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.input_form import PipeInputFormDescriptor, build_input_form
from pipelex.pipeline.pipe_io_contracts import build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.runtime_hub import get_console
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

INPUT_FORM_FILE_NAME = "input_form.json"
PIPE_IO_CONTRACTS_FILE_NAME = "pipe_io_contracts.json"
TEMPLATES_DIR_NAME = "inputs_template"
ENGINE_DIR_NAME = "engine"
MANIFEST_FILE_NAME = "manifest.json"
MAX_EXAMPLES_PER_DIVERGENCE = 3
MOCK_URL_PREFIX = "https://mock.invalid/"

COMPACT_SHAPE = "compact"
EXPLICIT_SHAPE = "explicit"

DIVERGENCE_REASONS: dict[str, str] = {
    "optional-field-included": (
        "The engine passes include_optional=False at the top of an input's own structure class and not "
        "through the recursion, so it hides an optional field at depth one and shows one nested deeper. "
        "The projection renders every field the descriptor states, at every depth."
    ),
    "file-leaf-not-expanded": (
        "The descriptor states a file-ish node as a leaf whose only fill-in value is a URL, while the "
        "engine expands the runtime content class and asks whoever fills the template in for a width, a "
        "mime type and a caption."
    ),
    "fixed-count-honoured": (
        "A Concept[N] slot renders N elements. The engine emits one whatever the count, and InputShaper "
        "then rejects that template with MultiplicityCountMismatchError, so the scaffold does not run."
    ),
    "text-named-url": (
        "The engine picks a placeholder by field name, so a text field merely named url or ending in _url "
        "renders as a URL. The projection reads the descriptor's kind instead."
    ),
    "scalar-vs-structured-native": (
        "A native whose pinned definition carries an optional field beside its required one — native.Date "
        "— no longer collapses to a single-key content once the optional field is rendered, so it stays "
        "an object where the engine unwrapped it to a bare scalar. A consequence of optional-field-included."
    ),
}


# The workspace-ledger item tracking the engine fix, where the difference is a defect rather than a
# difference of vantage. Named in the manifest so the corpus records not just that it departs from
# the engine but what would retire the departure. A class with no entry here is deliberate on both
# sides: `file-leaf-not-expanded` is the descriptor's vantage rather than an engine bug, and
# `scalar-vs-structured-native` is a consequence of `optional-field-included` rather than its own.
DIVERGENCE_ITEMS: dict[str, str] = {
    "text-named-url": "L-260830-dc48bf",
    "fixed-count-honoured": "L-260830-f3de29",
    "optional-field-included": "L-260830-d51440",
}


class DivergenceExample(BaseModel):
    """One worked site of a declared divergence, checkable in a consumer repo with no engine present.

    `expected` is the value the corpus holds at `path` in `<pipe_ref>.<shape>.json`, and `engine` the
    value the engine emits there — `null` when it emits nothing at all, which is unambiguous because a
    projected template never contains a null. A consumer repo checks a class has not lapsed by reading
    its own committed bytes at `path` and finding `expected` rather than `engine`.
    """

    model_config = ConfigDict(extra="forbid")

    pipe_ref: str
    shape: str
    path: str
    engine: Any = None
    expected: Any = None


class DeclaredDivergence(BaseModel):
    """One class of deliberate difference between the projection and the engine's own renderer.

    `ledger_item` names the workspace-ledger item tracking the engine fix, and is `null` for a class
    that is a difference of vantage rather than a defect — see `DIVERGENCE_ITEMS`.
    """

    model_config = ConfigDict(extra="forbid")

    divergence_id: str
    reason: str
    ledger_item: str | None = None
    occurrences: int
    examples: list[DivergenceExample] = Field(default_factory=empty_list_factory_of(DivergenceExample))


class CorpusManifest(BaseModel):
    """The corpus's own description of what it covers and where it departs from the engine."""

    model_config = ConfigDict(extra="forbid")

    bundles: list[str] = Field(default_factory=list)
    pipes: list[str] = Field(default_factory=list)
    shapes: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    divergences: list[DeclaredDivergence] = Field(default_factory=empty_list_factory_of(DeclaredDivergence))


def _write_json(*, path: Path, payload: Any) -> None:
    """The capture's byte discipline, shared with the input-semantics tracer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(*, path: Path, content: str) -> None:
    """A rendering is written verbatim: the corpus holds exactly what a projection must return."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class _DivergenceCollector:
    """Walks the engine's template beside the projection's and buckets every difference.

    Every difference must land in a declared class: an unclassified one means the projection changed
    in a way nobody wrote down, and the capture refuses rather than committing bytes no record explains.
    """

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.examples: dict[str, list[DivergenceExample]] = {}
        self.unclassified: list[str] = []

    def _record(self, *, divergence_id: str, path: list[str], engine: Any, expected: Any) -> None:
        self.counts[divergence_id] = self.counts.get(divergence_id, 0) + 1
        sites = self.examples.setdefault(divergence_id, [])
        if len(sites) < MAX_EXAMPLES_PER_DIVERGENCE:
            sites.append(
                DivergenceExample(
                    pipe_ref=path[0],
                    shape=path[1],
                    path=".".join(path[2:]),
                    engine=engine,
                    expected=expected,
                )
            )

    def compare(self, *, engine_value: Any, projected_value: Any, path: list[str]) -> None:
        """Bucket every leaf difference between one engine value and its projected counterpart."""
        # Handled before the dict/dict walk below, which iterates the *projected* keys and would
        # therefore find nothing to say about an empty projection. Deliberately not declared in
        # DIVERGENCE_REASONS: no bundle in the corpus reaches it today, so a capture that does must
        # write the declaration rather than inherit one nobody reviewed.
        if isinstance(engine_value, dict) and projected_value == {} and engine_value != {}:
            self._record(divergence_id="unknown-empty-object", path=path, engine=engine_value, expected=projected_value)
            return
        if (
            isinstance(engine_value, dict)
            and isinstance(projected_value, dict)
            and set(cast("dict[str, Any]", projected_value)) == {"url"}
            and len(cast("dict[str, Any]", engine_value)) > 1
            and "url" in cast("dict[str, Any]", engine_value)
        ):
            self._record(divergence_id="file-leaf-not-expanded", path=path, engine=engine_value, expected=projected_value)
            return
        if isinstance(engine_value, dict) and isinstance(projected_value, dict):
            engine_fields = cast("dict[str, Any]", engine_value)
            projected_fields = cast("dict[str, Any]", projected_value)
            for key in projected_fields:
                if key not in engine_fields:
                    self._record(divergence_id="optional-field-included", path=[*path, key], engine=None, expected=projected_fields[key])
                    continue
                self.compare(engine_value=engine_fields[key], projected_value=projected_fields[key], path=[*path, key])
            return
        if isinstance(engine_value, list) and isinstance(projected_value, list):
            engine_items = cast("list[Any]", engine_value)
            projected_items = cast("list[Any]", projected_value)
            if len(engine_items) == 1 and len(projected_items) > 1:
                self._record(divergence_id="fixed-count-honoured", path=path, engine=engine_items, expected=projected_items)
            for index in range(min(len(engine_items), len(projected_items))):
                self.compare(engine_value=engine_items[index], projected_value=projected_items[index], path=[*path, str(index)])
            return
        if engine_value == projected_value:
            return
        if isinstance(engine_value, str) and engine_value.startswith(MOCK_URL_PREFIX) and isinstance(projected_value, str):
            self._record(divergence_id="text-named-url", path=path, engine=engine_value, expected=projected_value)
            return
        if isinstance(engine_value, dict) or isinstance(projected_value, dict):
            self._record(divergence_id="scalar-vs-structured-native", path=path, engine=engine_value, expected=projected_value)
            return
        self.unclassified.append(f"{'.'.join(path)}: engine={engine_value!r} projected={projected_value!r}")

    def declared(self) -> list[DeclaredDivergence]:
        """The divergence record, refusing a class that is undeclared or has stopped occurring."""
        undeclared = sorted(set(self.counts) - set(DIVERGENCE_REASONS))
        if undeclared:
            msg = f"Undeclared divergence class(es) {undeclared}: add the reason to DIVERGENCE_REASONS or fix the projection."
            raise ValueError(msg)
        lapsed = sorted(set(DIVERGENCE_REASONS) - set(self.counts))
        if lapsed:
            msg = f"Declared divergence class(es) {lapsed} no longer occur — delete the entry, the engine agrees now."
            raise ValueError(msg)
        return [
            DeclaredDivergence(
                divergence_id=divergence_id,
                reason=DIVERGENCE_REASONS[divergence_id],
                ledger_item=DIVERGENCE_ITEMS.get(divergence_id),
                occurrences=self.counts[divergence_id],
                examples=self.examples.get(divergence_id, []),
            )
            for divergence_id in sorted(self.counts)
        ]


def _render_projection(*, descriptor: PipeInputFormDescriptor, explicit: bool) -> tuple[str, str]:
    """The projected template for one pipe and shape, as the JSON and TOML bytes the corpus holds."""
    template = project_inputs_template(descriptor=descriptor, explicit=explicit)
    json_text = json.dumps(template, indent=2, ensure_ascii=False)
    if explicit:
        toml_text = serialize_inputs_template_to_toml(template)
    else:
        toml_text = serialize_inputs_template_to_toml(template, light=True, concept_comments=project_concept_comments(descriptor=descriptor))
    return json_text, toml_text


def _capture_pipe(
    *,
    pipe: PipeAbstract,
    descriptor: PipeInputFormDescriptor,
    output_dir: Path,
    collector: _DivergenceCollector,
) -> None:
    """Write one pipe's four projected renderings, the engine's four, and bucket the differences."""
    templates_dir = output_dir / TEMPLATES_DIR_NAME
    engine_dir = output_dir / ENGINE_DIR_NAME
    for explicit in (False, True):
        shape = EXPLICIT_SHAPE if explicit else COMPACT_SHAPE
        json_text, toml_text = _render_projection(descriptor=descriptor, explicit=explicit)
        _write_text(path=templates_dir / f"{pipe.pipe_ref}.{shape}.json", content=json_text)
        _write_text(path=templates_dir / f"{pipe.pipe_ref}.{shape}.toml", content=toml_text)
        _write_text(path=engine_dir / f"{pipe.pipe_ref}.{shape}.json", content=render_inputs(pipe, explicit=explicit))
        _write_text(path=engine_dir / f"{pipe.pipe_ref}.{shape}.toml", content=render_inputs_toml(pipe, explicit=explicit))
        collector.compare(
            engine_value=build_inputs_template(pipe, explicit=explicit),
            projected_value=project_inputs_template(descriptor=descriptor, explicit=explicit),
            path=[pipe.pipe_ref, shape],
        )


async def generate_projection_corpus(*, bundle_paths: list[Path], output_dir: Path) -> CorpusManifest:
    """Validate the given bundles and write the whole projection fixture corpus.

    Args:
        bundle_paths: The `.mthds` files to load as one batch. Their order fixes the key order of the
            emitted maps, so it is part of the capture: pass them the way the corpus README records.
        output_dir: Directory receiving the corpus (created if missing).

    Returns:
        The manifest, also written to the corpus.

    Raises:
        ValidateBundleError: When a bundle is invalid — the corpus requires valid bundles.
        ValueError: When a difference from the engine is undeclared, or a declared one has lapsed.
    """
    mthds_contents = [bundle_path.read_text(encoding="utf-8") for bundle_path in bundle_paths]
    mthds_sources = [str(bundle_path) for bundle_path in bundle_paths]

    output_dir.mkdir(parents=True, exist_ok=True)
    # Both directories accumulate one file per pipe and shape, so a rerun must replace them wholesale:
    # a leftover rendering from a renamed pipe would read as part of the current corpus.
    for stale_dir_name in (TEMPLATES_DIR_NAME, ENGINE_DIR_NAME):
        stale_dir = output_dir / stale_dir_name
        if stale_dir.is_dir():
            shutil.rmtree(stale_dir)

    prev_library_id = get_current_library_id_or_none()
    validation_library_id: str | None = None
    collector = _DivergenceCollector()
    try:
        result = await validate_bundle(mthds_contents=mthds_contents, mthds_sources=mthds_sources)
        validation_library_id = get_current_library_id_or_none()

        input_form = build_input_form(result.pipes)
        _write_json(
            path=output_dir / INPUT_FORM_FILE_NAME,
            payload={pipe_ref: descriptor.model_dump(mode="json") for pipe_ref, descriptor in input_form.items()},
        )
        io_contracts = build_pipe_io_contracts(result.pipes)
        _write_json(
            path=output_dir / PIPE_IO_CONTRACTS_FILE_NAME,
            payload={pipe_ref: contract.model_dump(mode="json") for pipe_ref, contract in io_contracts.items()},
        )
        for pipe in result.pipes:
            _capture_pipe(pipe=pipe, descriptor=input_form[pipe.pipe_ref], output_dir=output_dir, collector=collector)
    finally:
        if validation_library_id is not None and validation_library_id != prev_library_id:
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            get_library_manager().teardown(library_id=validation_library_id)

    if collector.unclassified:
        listed = "\n  ".join(collector.unclassified[:20])
        msg = f"The projection differs from the engine at site(s) no declared divergence explains:\n  {listed}"
        raise ValueError(msg)

    manifest = CorpusManifest(
        bundles=[bundle_path.name for bundle_path in bundle_paths],
        pipes=sorted(input_form),
        shapes=[COMPACT_SHAPE, EXPLICIT_SHAPE],
        formats=["json", "toml"],
        divergences=collector.declared(),
    )
    _write_json(path=output_dir / TEMPLATES_DIR_NAME / MANIFEST_FILE_NAME, payload=manifest.model_dump(mode="json"))
    return manifest


def generate_projection_corpus_cmd(*, bundle_paths: list[Path], output_dir: Path) -> None:
    """CLI wrapper: boot Pipelex, write the corpus, report what it covers and where it diverges."""
    console = get_console()
    for bundle_path in bundle_paths:
        if not bundle_path.is_file():
            console.print(f"[red]Bundle file not found: {bundle_path}[/red]")
            sys.exit(2)

    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False, needs_model_specs=True)
    try:
        manifest = asyncio.run(generate_projection_corpus(bundle_paths=bundle_paths, output_dir=output_dir))
    except ValidateBundleError as exc:
        console.print(f"[red]Bundle validation failed — the corpus requires valid bundles:[/red]\n{exc}")
        sys.exit(1)
    except ValueError as exc:
        console.print(f"[red]Divergence record is out of date:[/red]\n{exc}")
        sys.exit(1)
    except PipelexError as exc:
        console.print(f"[red]Corpus generation failed:[/red]\n{exc}")
        sys.exit(1)
    finally:
        Pipelex.teardown_if_needed()

    console.print(f"[green]✓ Projection corpus written to {output_dir}[/green]")
    console.print(f"  pipes: {len(manifest.pipes)}, each in {len(manifest.shapes)} shapes × {len(manifest.formats)} formats")
    for divergence in manifest.divergences:
        console.print(f"  divergence {divergence.divergence_id}: {divergence.occurrences} site(s)")
    console.print(f"  the engine's own renderings are under {ENGINE_DIR_NAME}/ — for review, not for committing")
