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

Every template is also handed straight back to the runtime — `InputShaper.shape`, assembled the way
an entry-pipe run assembles it — because a fill-in template exists to be filled in and run. A refusal
no `EXPECTED_UNSHAPEABLE` entry declares fails this command too, on the same declared-never-discovered
discipline: the corpus must not pin bytes the engine rejects.
"""

import asyncio
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict, Field

from pipelex.base_exceptions import PipelexError
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.dev_cli.commands.projection_reference import (
    ENVELOPE_CONTENT_KEY,
    keeps_envelope,
    project_concept_comments,
    project_inputs_template,
)
from pipelex.cli.error_handlers import ErrorContext
from pipelex.interpreter_hub import (
    clear_current_library,
    get_concept_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.kernel.memory_ops import shape_inputs
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.rendering.input_renderer import (
    build_inputs_template,
    render_inputs,
    render_inputs_toml,
    serialize_inputs_template_to_toml,
)
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.input_form import ListField, PipeInputFormDescriptor, build_input_form
from pipelex.pipeline.pipe_io_contracts import build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.runtime_hub import get_console
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

if TYPE_CHECKING:
    from mthds.protocol.pipeline_inputs import PipelineInputs

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
    "unknown-empty-object": (
        "An unknown node renders as the empty object, because the descriptor withholds the payload shape "
        "at that position and a projection that invented one would stop projecting the descriptor. The "
        "engine reflects the runtime content class instead and fills a required dict with a sample "
        "key/value pair whoever fills the template in has to delete. The empty object is re-shapable: the "
        "round-trip takes it back."
    ),
    "object-native-keeps-envelope": (
        "A native whose pinned definition carries an optional field beside its required one — native.Date — "
        "renders as an object once the optional field is included, and the shaper's bare-value arm dispatches "
        "a native on its scalar kind, so the object form is only re-shapable inside its {concept, content} "
        "envelope. The projection keeps that envelope; the engine unwraps to a bare scalar, which it can only "
        "do because it drops the optional field. A consequence of optional-field-included."
    ),
}


# The workspace-ledger item tracking the engine fix, where the difference is a defect rather than a
# difference of vantage. Named in the manifest so the corpus records not just that it departs from
# the engine but what would retire the departure. A class with no entry here is deliberate on both
# sides: `file-leaf-not-expanded` and `unknown-empty-object` are the descriptor's vantage rather than
# engine bugs, and `object-native-keeps-envelope` is a consequence of `optional-field-included`
# rather than its own.
DIVERGENCE_ITEMS: dict[str, str] = {
    "text-named-url": "L-260830-dc48bf",
    "fixed-count-honoured": "L-260830-f3de29",
    "optional-field-included": "L-260830-d51440",
}


# The templates the input shaper refuses today, each against the workspace-ledger item tracking the
# gap that makes it refuse. Declared here for the same reason the divergences are: a refusal with no
# entry fails the capture rather than reaching two consumer repos as contract bytes, and an entry
# whose template has started shaping fails it too — so closing the gap retires its declaration
# deliberately instead of leaving the manifest claiming a defect that no longer exists.
#
# Two gaps are declared. `L-260830-191719` is the nested-list descriptor gap (`matrix` in `Widget`),
# which takes both shapes of both probe pipes that reach it. `L-260902-10eb56` is the `native.Anything`
# slot in `scaffold_open_natives`: its template value is the empty object every `unknown` node renders,
# and the shaper accepts a bare string alone at an `Anything` position — so the contract publishes a
# template the runtime cannot take back. Each fix deletes its own entries and regenerates.
EXPECTED_UNSHAPEABLE: dict[tuple[str, str], str] = {
    ("input_semantics_probe.probe_markers", COMPACT_SHAPE): "L-260830-191719",
    ("input_semantics_probe.probe_markers", EXPLICIT_SHAPE): "L-260830-191719",
    ("input_semantics_probe.probe_single", COMPACT_SHAPE): "L-260830-191719",
    ("input_semantics_probe.probe_single", EXPLICIT_SHAPE): "L-260830-191719",
    ("input_semantics_scaffold.scaffold_open_natives", COMPACT_SHAPE): "L-260902-10eb56",
    ("input_semantics_scaffold.scaffold_open_natives", EXPLICIT_SHAPE): "L-260902-10eb56",
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


class UnshapeableEntry(BaseModel):
    """One template this capture pins that the input shaper refuses to take back.

    A fact of the capture, stated so a consumer repo reads it off the manifest rather than
    discovering it by running the template. `error_type` is the error's class name, which is
    contract-stable — the error-identity snapshot makes a rename a reviewable diff — while the
    message is wording that would churn these committed bytes across pydantic versions, so it stays
    on the console. `ledger_item` names the workspace-ledger item whose fix retires this entry.
    """

    model_config = ConfigDict(extra="forbid")

    pipe_ref: str
    shape: str
    error_type: str
    ledger_item: str


class CorpusManifest(BaseModel):
    """The corpus's own description of what it covers and where it departs from the engine."""

    model_config = ConfigDict(extra="forbid")

    bundles: list[str] = Field(default_factory=list)
    pipes: list[str] = Field(default_factory=list)
    shapes: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    divergences: list[DeclaredDivergence] = Field(default_factory=empty_list_factory_of(DeclaredDivergence))
    unshapeable: list[UnshapeableEntry] = Field(default_factory=empty_list_factory_of(UnshapeableEntry))


def _write_json(*, path: Path, payload: Any) -> None:
    """The capture's byte discipline, shared with the input-semantics tracer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(*, path: Path, content: str) -> None:
    """A rendering is written verbatim: the corpus holds exactly what a projection must return."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _engine_dict_placeholder(*, path: list[str]) -> dict[str, str]:
    """What the engine renders at a dict-typed field, which is exactly where the descriptor says `unknown`.

    `ConceptRepresentationGenerator._generate_dict_value` returns `{f"{name}_key": f"{name}_value"}`,
    and `generate_field_value` is its only caller — dispatched on `origin is dict`, the same test that
    makes the input-form deriver state the node as `unknown`. A dict inside a list never reaches it
    (`_generate_list_value` routes items through `_generate_basic_value`, which returns no dicts), so
    the placeholder is always keyed by the field's own name — the last segment of the walk's path.
    """
    field_name = path[-1]
    return {f"{field_name}_key": f"{field_name}_value"}


class DivergenceCollector:
    """Walks the engine's template beside the projection's and buckets every difference.

    Every difference must land in a declared class: an unclassified one means the projection changed
    in a way nobody wrote down, and the capture refuses rather than committing bytes no record explains.
    The walk meets *both* sides' keys — a field the projection stopped rendering is a difference as
    much as one it added — so nothing reaches the manifest by being skipped.

    **What the classification rests on, and where it stops.** Each arm reads the two values' shapes,
    plus the one descriptor fact shape cannot supply: the declared `item_count` of a fixed-count slot
    (`register_fixed_counts`). That is enough to keep a regression out of the two classes whose arms
    would otherwise swallow one whole — `file-leaf-not-expanded`, which used to return without ever
    comparing the URL both sides carry, and `fixed-count-honoured`, which used to fire on any list
    longer than the engine's one element. It is not enough to tell every *wrong* value at a site that
    already carries a class from the right one: a projection that invents a field still reads as
    `optional-field-included`, and a garbled placeholder at a url-named text field still reads as
    `text-named-url`. Separating those needs each node's kind and presence threaded through the whole
    walk, which is a redesign of the walk rather than a fix to it.
    """

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.examples: dict[str, list[DivergenceExample]] = {}
        self.unclassified: list[str] = []
        self._fixed_counts: dict[tuple[str, ...], int] = {}

    def register_fixed_counts(self, *, pipe_ref: str, descriptor: PipeInputFormDescriptor) -> None:
        """Record where this pipe's descriptor declares a fixed element count, by the path the walk meets.

        The one descriptor fact the classification cannot do without: `fixed-count-honoured` has to
        separate a `Concept[N]` slot rendering its N elements from a projection rendering the wrong
        number, and the two are indistinguishable by value shape alone.

        Only a top-level slot can carry a count — `InputFormDeriver.derive_slot` is the sole site
        that passes `item_count`, and both nested `ListField` constructions leave it `None` — so the
        map holds one entry per fixed slot, at the exact path its list sits at in each shape. A
        nested list therefore matches nothing, which is the safe direction: a length mismatch there
        is unclassified rather than absorbed.
        """
        for field in descriptor.fields:
            if not isinstance(field, ListField) or field.item_count is None:
                continue
            # The explicit shape always wraps the slot; the compact shape unwraps unless the slot is
            # one the shaper cannot rebuild from a bare value, which keeps its envelope.
            self._fixed_counts[pipe_ref, EXPLICIT_SHAPE, field.name, ENVELOPE_CONTENT_KEY] = field.item_count
            if keeps_envelope(node=field):
                self._fixed_counts[pipe_ref, COMPACT_SHAPE, field.name, ENVELOPE_CONTENT_KEY] = field.item_count
            else:
                self._fixed_counts[pipe_ref, COMPACT_SHAPE, field.name] = field.item_count

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

    def _unclassify(self, *, path: list[str], engine: Any, projected: Any) -> None:
        """A difference no declared class explains — one of these fails the whole capture."""
        self.unclassified.append(f"{'.'.join(path)}: engine={engine!r} projected={projected!r}")

    def compare(self, *, engine_value: Any, projected_value: Any, path: list[str]) -> None:
        """Bucket every leaf difference between one engine value and its projected counterpart."""
        # Handled before the dict/dict walk below, which would report the same thing one key at a
        # time: a projection rendering nothing where the engine renders an object is one fact, not N.
        # Reached by the required dict inside `native.JSON` — `json_obj`, whose descriptor node is
        # `unknown` like every dict field, so the projection renders the empty object while the
        # engine fills it with a sample key. The corpus's optional dict fields never reach here:
        # the engine drops those entirely, which is `optional-field-included`.
        #
        # Recognised by the engine's own placeholder rather than by the empty object alone, because
        # `{}` is what the projection renders for an `object` node with no fields as much as for an
        # `unknown` one: a shape-only arm would file a projection that collapsed a populated object
        # into this declared class and return without ever walking the subtree — the whole-difference
        # swallow the file-leaf and fixed-count arms were repaired for. The placeholder is exact, not
        # a heuristic: `ConceptRepresentationGenerator._generate_dict_value` renders `{name_key:
        # name_value}` and is dispatched from one site only, on `origin is dict`, which is precisely
        # what makes the descriptor node `unknown`. A non-matching value falls through to the dict
        # walk below, where each key the projection dropped is `engine-only-field` and the capture
        # refuses.
        if isinstance(engine_value, dict) and projected_value == {} and engine_value == _engine_dict_placeholder(path=path):
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
            # The expansion is the declared difference; the URL both sides carry is not part of it,
            # and is compared strictly here rather than recursed into. Plain recursion would hand a
            # regressed placeholder to the `text-named-url` arm below, whose only test is that the
            # *engine* value is a mock URL — so the regression would be absorbed into a class that
            # then explains it away. Both sides derive the same URL today.
            for key in sorted(set(cast("dict[str, Any]", projected_value)) & set(cast("dict[str, Any]", engine_value))):
                engine_leaf = cast("dict[str, Any]", engine_value)[key]
                projected_leaf = cast("dict[str, Any]", projected_value)[key]
                if engine_leaf != projected_leaf:
                    self._unclassify(path=[*path, key], engine=engine_leaf, projected=projected_leaf)
            return
        if isinstance(engine_value, dict) and isinstance(projected_value, dict):
            engine_fields = cast("dict[str, Any]", engine_value)
            projected_fields = cast("dict[str, Any]", projected_value)
            # Walked before the projected keys, because the walk below iterates those and would
            # otherwise skip a field the projection stopped rendering entirely — a projection
            # regression that reached neither a class nor `unclassified`. Deliberately absent from
            # DIVERGENCE_REASONS: no bundle in the corpus reaches it today, so a capture that does
            # must write the declaration itself rather than inherit one nobody reviewed.
            for key in engine_fields:
                if key not in projected_fields:
                    self._record(divergence_id="engine-only-field", path=[*path, key], engine=engine_fields[key], expected=None)
            for key in projected_fields:
                if key not in engine_fields:
                    self._record(divergence_id="optional-field-included", path=[*path, key], engine=None, expected=projected_fields[key])
                    continue
                self.compare(engine_value=engine_fields[key], projected_value=projected_fields[key], path=[*path, key])
            return
        if isinstance(engine_value, list) and isinstance(projected_value, list):
            engine_items = cast("list[Any]", engine_value)
            projected_items = cast("list[Any]", projected_value)
            if len(engine_items) != len(projected_items):
                # `fixed-count-honoured` is the slot's *declared* count being met, which the lengths
                # alone cannot say: without the descriptor, a `[2]` slot rendering four elements and
                # a variable `[]` slot rendering two both read as "more than the engine's one".
                declared_count = self._fixed_counts.get(tuple(path))
                if len(engine_items) == 1 and declared_count is not None and len(projected_items) == declared_count:
                    self._record(divergence_id="fixed-count-honoured", path=path, engine=engine_items, expected=projected_items)
                else:
                    self._unclassify(path=path, engine=engine_items, projected=projected_items)
            for index in range(min(len(engine_items), len(projected_items))):
                self.compare(engine_value=engine_items[index], projected_value=projected_items[index], path=[*path, str(index)])
            return
        if engine_value == projected_value:
            return
        if isinstance(engine_value, str) and engine_value.startswith(MOCK_URL_PREFIX) and isinstance(projected_value, str):
            self._record(divergence_id="text-named-url", path=path, engine=engine_value, expected=projected_value)
            return
        if isinstance(engine_value, dict) or isinstance(projected_value, dict):
            self._record(divergence_id="object-native-keeps-envelope", path=path, engine=engine_value, expected=projected_value)
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


class ShapingGate:
    """Hands every projected template back to the runtime and refuses one nobody declared unshapeable.

    A template is pinned to be filled in and run, so surviving `InputShaper.shape` is part of what the
    corpus asserts — and nothing else checks it. Twice the corpus committed bytes the runtime rejects
    outright, and both times a human review round caught it rather than the capture; the second time
    the divergence gate absorbed the broken sites into a declared class and exited 0, because a
    difference from the engine and a value the engine refuses are not the same question.

    The verdicts are collected against an injected registry so the whole decision can be put to cases
    no corpus bundle produces. The rule is symmetric, exactly as `DivergenceCollector.declared()` is:
    an undeclared refusal fails the capture, and a declaration whose template has started shaping
    fails it too.
    """

    def __init__(self, *, registry: dict[tuple[str, str], str] | None = None) -> None:
        self.registry = EXPECTED_UNSHAPEABLE if registry is None else registry
        self.verdicts: dict[tuple[str, str], Exception | None] = {}

    @property
    def failures(self) -> dict[tuple[str, str], Exception]:
        """The refusals, by the `(pipe_ref, shape)` key the registry is written in."""
        return {key: error for key, error in self.verdicts.items() if error is not None}

    @property
    def passing_count(self) -> int:
        """How many templates went back through the shaper cleanly — printed, never committed."""
        return len(self.verdicts) - len(self.failures)

    def record(self, *, pipe_ref: str, shape: str, error: Exception | None) -> None:
        """Record one round-trip's verdict, `None` being the template the shaper took back."""
        self.verdicts[pipe_ref, shape] = error

    def round_trip(self, *, pipe: PipeAbstract, shape: str, template: dict[str, Any]) -> None:
        """Shape one projected template the way an entry-pipe run shapes a caller's inputs.

        The same assembly as `execution_seams`: the pipe's own declared inputs as the signature and
        its domain as the search scope. Offline — the file-ish arms wrap a URL without fetching it —
        and the template is copied first, so nothing the shaper does can reach the bytes just written.
        """
        try:
            shape_inputs(
                inputs=cast("PipelineInputs", deepcopy(template)),
                concept_provider=get_concept_library(),
                input_specs=pipe.inputs,
                search_scope=pipe.domain_code,
            )
        except Exception as exc:  # ruff: ignore[blind-except]
            # (2) Unbounded surface: the shaper's explicit arm hands values straight to pydantic on
            # a generated structure class, so a raw ValidationError escapes untyped today
            # (L-260831-1e1a71). Enumerating the surface would make this gate blind to exactly the
            # refusals it exists to catch — any refusal at all is the verdict it records.
            self.record(pipe_ref=pipe.pipe_ref, shape=shape, error=exc)
        else:
            self.record(pipe_ref=pipe.pipe_ref, shape=shape, error=None)

    def declared(self) -> list[UnshapeableEntry]:
        """The unshapeable record, refusing an undeclared refusal and a declaration that has lapsed."""
        failures = self.failures
        undeclared = sorted(key for key in failures if key not in self.registry)
        if undeclared:
            # Parenthesised, not bracketed: this message is printed through the Rich console, which
            # reads a `[compact]` as markup and eats it — leaving two shapes of one pipe as two
            # identical lines, each missing the half of the address that says which one failed.
            listed = "\n  ".join(
                f"{pipe_ref} ({shape}): {type(failures[pipe_ref, shape]).__name__}: {str(failures[pipe_ref, shape]).splitlines()[0]}"
                for pipe_ref, shape in undeclared
            )
            msg = (
                "The input shaper refuses template(s) with no EXPECTED_UNSHAPEABLE entry declaring them — "
                f"fix the projection, or declare the gap and name the item tracking it:\n  {listed}"
            )
            raise ValueError(msg)
        # Two ways a declaration can go stale, and they call for opposite actions, so they are worded
        # apart rather than lumped into one "delete the entry". A template that started shaping is a
        # closed gap; one this capture never walked at all is a key that no longer addresses anything
        # — a renamed pipe, or a run over a subset of the bundles — and deleting it there would drop
        # a gap that is still open.
        shaping_now = sorted(key for key in self.registry if key in self.verdicts and key not in failures)
        if shaping_now:
            msg = f"Declared unshapeable template(s) {shaping_now} now shape — delete the EXPECTED_UNSHAPEABLE entry, the gap closed."
            raise ValueError(msg)
        unwalked = sorted(key for key in self.registry if key not in self.verdicts)
        if unwalked:
            msg = (
                f"Declared unshapeable template(s) {unwalked} were never walked by this capture — "
                "the key names no pipe and shape this run produced. Re-key the EXPECTED_UNSHAPEABLE entry "
                "if the pipe was renamed, or pass every bundle the corpus is generated from; deleting it "
                "would drop a gap that is still open."
            )
            raise ValueError(msg)
        return [
            UnshapeableEntry(
                pipe_ref=pipe_ref,
                shape=shape,
                error_type=type(failures[pipe_ref, shape]).__name__,
                ledger_item=self.registry[pipe_ref, shape],
            )
            for pipe_ref, shape in sorted(failures)
        ]


def _render_projection(*, descriptor: PipeInputFormDescriptor, explicit: bool) -> tuple[dict[str, Any], str, str]:
    """The projected template for one pipe and shape, with the JSON and TOML bytes the corpus holds.

    The template itself is returned beside its renderings because both gates read it: the divergence
    collector compares it against the engine's, and the shaping gate hands it back to the runtime.
    """
    template = project_inputs_template(descriptor=descriptor, explicit=explicit)
    json_text = json.dumps(template, indent=2, ensure_ascii=False)
    if explicit:
        toml_text = serialize_inputs_template_to_toml(template)
    else:
        toml_text = serialize_inputs_template_to_toml(template, light=True, concept_comments=project_concept_comments(descriptor=descriptor))
    return template, json_text, toml_text


def _capture_pipe(
    *,
    pipe: PipeAbstract,
    descriptor: PipeInputFormDescriptor,
    output_dir: Path,
    collector: DivergenceCollector,
    shaping_gate: ShapingGate,
) -> None:
    """Write one pipe's four projected renderings, the engine's four, and bucket the differences."""
    templates_dir = output_dir / TEMPLATES_DIR_NAME
    engine_dir = output_dir / ENGINE_DIR_NAME
    collector.register_fixed_counts(pipe_ref=pipe.pipe_ref, descriptor=descriptor)
    for explicit in (False, True):
        shape = EXPLICIT_SHAPE if explicit else COMPACT_SHAPE
        template, json_text, toml_text = _render_projection(descriptor=descriptor, explicit=explicit)
        _write_text(path=templates_dir / f"{pipe.pipe_ref}.{shape}.json", content=json_text)
        _write_text(path=templates_dir / f"{pipe.pipe_ref}.{shape}.toml", content=toml_text)
        # Before the empty-form skip below: an empty descriptor projects to `{}`, which the shaper
        # takes back trivially, and a verdict recorded there is what keeps the pipe in the walk.
        shaping_gate.round_trip(pipe=pipe, shape=shape, template=template)
        if not descriptor.fields:
            # An empty input form is a valid form — `PipeInputFormDescriptor` says so — and the
            # projection renders it as `{}`. Only the engine's own renderer refuses one, raising
            # NoInputsRequiredError, so the projected half is the whole capture here and there is
            # nothing to compare it against.
            continue
        _write_text(path=engine_dir / f"{pipe.pipe_ref}.{shape}.json", content=render_inputs(pipe, explicit=explicit))
        _write_text(path=engine_dir / f"{pipe.pipe_ref}.{shape}.toml", content=render_inputs_toml(pipe, explicit=explicit))
        collector.compare(
            engine_value=build_inputs_template(pipe, explicit=explicit),
            projected_value=template,
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
        ValueError: When a difference from the engine is undeclared, or a declared one has lapsed;
            likewise when the input shaper refuses an undeclared template, or takes back one the
            registry still declares unshapeable.
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
    collector = DivergenceCollector()
    shaping_gate = ShapingGate()
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
            _capture_pipe(
                pipe=pipe,
                descriptor=input_form[pipe.pipe_ref],
                output_dir=output_dir,
                collector=collector,
                shaping_gate=shaping_gate,
            )
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
        unshapeable=shaping_gate.declared(),
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
        console.print(f"[red]The corpus's own record is out of date:[/red]\n{exc}")
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
    # The passing verdicts are a count rather than a list: the corpus is almost entirely passing
    # verdicts, and a template the shaper takes back is the state every entry below is working towards.
    round_trips = len(manifest.pipes) * len(manifest.shapes)
    console.print(f"  round-tripped through the input shaper: {round_trips - len(manifest.unshapeable)}/{round_trips} shape cleanly")
    for entry in manifest.unshapeable:
        # Parenthesised, not bracketed: the console renders Rich markup, which eats a `[compact]`.
        console.print(f"  unshapeable {entry.pipe_ref} ({entry.shape}): {entry.error_type} — tracked by {entry.ledger_item}")
    console.print(f"  the engine's own renderings are under {ENGINE_DIR_NAME}/ — for review, not for committing")
