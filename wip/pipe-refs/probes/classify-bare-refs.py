# ruff: noqa: INP001 - a standalone probe script, deliberately not a package
"""Classify every bare in-body reference in a corpus of `.mthds` bundles.

Reads TOML and nothing else — no `pipelex` import, no library load — so the classification is a
property of the authored text, not of any resolver's behaviour. That is the point: it measures what
the corpus *asks for*, which is what decides how expensive each direction of the bare-ref fix is.

For every merge unit (see `merge_unit_of`), the probe builds `code -> {domains that declare it}` and
puts each bare in-body reference in one of four buckets:

    own-only      the referring domain declares it, nobody else       spec and runtime agree
    sibling-only  ONLY some other domain declares it                  spec: ERROR, runtime: resolves
    both          the referring domain AND another declare it         spec: the own one, runtime: RAISES
    nowhere       nobody declares it                                  both error

`sibling-only` counts the references that would BREAK if the runtime were tightened to the spec.
`both` counts the references that are broken TODAY and would START WORKING under the spec.

Usage:

    python wip/pipe-refs/probes/classify-bare-refs.py <root> [<root> ...]

Each root is a directory tree to walk. Pass `.` for this repository's own corpus; pass sibling
checkouts to widen it.
"""

import pathlib
import sys
import tomllib
from collections import defaultdict
from typing import Any, NamedTuple

# Native concept codes take priority over any declaration (mthds/docs/spec/namespace-resolution.md
# § "Resolution Order for Bare Concept References", step 1), so a bare `Text` is never a lookup.
NATIVE_CONCEPT_CODES = frozenset(
    {
        "Dynamic",
        "Text",
        "Image",
        "Document",
        "Html",
        "TextAndImages",
        "Number",
        "YesNo",
        "Date",
        "Time",
        "Page",
        "JSON",
        "SearchResult",
        "Anything",
        "Composite",
    }
)

# pipelex/pipe_controllers/condition/special_outcome.py
SPECIAL_OUTCOMES = frozenset({"fail", "continue"})

MANIFEST_NAME = "METHODS.toml"
SKIPPED_DIR_NAMES = frozenset({".git", ".venv", "node_modules", "__pycache__", "dist", "build"})
BUCKETS = ("own-only", "sibling-only", "both", "nowhere")
REPORTED_BUCKETS = ("sibling-only", "both", "nowhere")


class Bundle(NamedTuple):
    path: pathlib.Path
    domain: str
    pipes: dict[str, Any]
    concepts: dict[str, Any]


class Reference(NamedTuple):
    code: str
    where: str


def merge_unit_of(path: pathlib.Path, *, root: pathlib.Path) -> pathlib.Path:
    """The directory whose bundles share one namespace with this one.

    A package (a tree with a `METHODS.toml` manifest) merges as a whole; a loose bundle merges with
    the other bundles sitting beside it, which is how a `-L <dir>` load behaves. This is an
    approximation of the loader, and it is the probe's main limitation — see the doc's "What this
    measurement does not cover".
    """
    for ancestor in [path.parent, *path.parent.parents]:
        if (ancestor / MANIFEST_NAME).is_file():
            return ancestor
        if ancestor == root:
            break
    return path.parent


def strip_multiplicity(ref: str) -> str:
    """Drop the presence and multiplicity markers a concept ref may carry (`Foo[]?` -> `Foo`)."""
    bare = ref.strip()
    while bare.endswith(("?", "!")):
        bare = bare[:-1]
    if bare.endswith("]") and "[" in bare:
        bare = bare[: bare.rindex("[")]
    return bare


def bare_pipe_references(pipe_body: dict[str, Any]) -> list[Reference]:
    """Every in-body pipe reference this pipe names, in the blueprints' authored field names."""
    found: list[Reference] = []
    for step in pipe_body.get("steps") or []:
        if isinstance(step, dict) and isinstance(step.get("pipe"), str):
            found.append(Reference(code=step["pipe"], where="step"))
    for branch in pipe_body.get("branches") or []:
        if isinstance(branch, dict) and isinstance(branch.get("pipe"), str):
            found.append(Reference(code=branch["pipe"], where="branch"))
    outcomes = pipe_body.get("outcomes")
    if isinstance(outcomes, dict):
        for outcome_ref in outcomes.values():
            if isinstance(outcome_ref, str):
                found.append(Reference(code=outcome_ref, where="outcome"))
    for field_name in ("default_outcome", "branch_pipe_code"):
        field_value = pipe_body.get(field_name)
        if isinstance(field_value, str):
            found.append(Reference(code=field_value, where=field_name))
    return [ref for ref in found if ref.code not in SPECIAL_OUTCOMES]


def _structure_field_references(field_value: Any, *, where: str) -> list[Reference]:
    if not isinstance(field_value, dict):
        return []
    found: list[Reference] = []
    for key in ("concept_ref", "item_concept_ref"):
        nested = field_value.get(key)
        if isinstance(nested, str):
            found.append(Reference(code=nested, where=where))
    return found


def bare_concept_references(bundle: Bundle) -> list[Reference]:
    """Every in-body concept reference the bundle names: pipe inputs/output, refines, structures."""
    found: list[Reference] = []
    for pipe_code, pipe_body in bundle.pipes.items():
        if not isinstance(pipe_body, dict):
            continue
        inputs = pipe_body.get("inputs")
        if isinstance(inputs, dict):
            for input_ref in inputs.values():
                if isinstance(input_ref, str):
                    found.append(Reference(code=input_ref, where=f"{pipe_code}.inputs"))
        output = pipe_body.get("output")
        if isinstance(output, str):
            found.append(Reference(code=output, where=f"{pipe_code}.output"))
    for concept_code, concept_body in bundle.concepts.items():
        if not isinstance(concept_body, dict):
            continue
        refines = concept_body.get("refines")
        if isinstance(refines, str):
            found.append(Reference(code=refines, where=f"{concept_code}.refines"))
        structure = concept_body.get("structure")
        if isinstance(structure, dict):
            for field_name, field_value in structure.items():
                found.extend(_structure_field_references(field_value, where=f"{concept_code}.{field_name}"))
    return found


def read_bundles(root: pathlib.Path) -> dict[pathlib.Path, list[Bundle]]:
    """Group every readable `.mthds` bundle under `root` by the merge unit it belongs to."""
    by_unit: dict[pathlib.Path, list[Bundle]] = defaultdict(list)
    for path in sorted(root.rglob("*.mthds")):
        if any(part in SKIPPED_DIR_NAMES for part in path.parts):
            continue
        try:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            # A bundle this probe cannot parse is not this measurement's subject.
            continue
        domain = document.get("domain")
        if not isinstance(domain, str):
            continue
        pipes = document.get("pipe")
        concepts = document.get("concept")
        by_unit[merge_unit_of(path, root=root)].append(
            Bundle(
                path=path,
                domain=domain,
                pipes=pipes if isinstance(pipes, dict) else {},
                concepts=concepts if isinstance(concepts, dict) else {},
            )
        )
    return by_unit


class Tally:
    def __init__(self, *, label: str) -> None:
        self.label = label
        self.counts: dict[str, int] = defaultdict(int)
        self.hits: dict[str, list[str]] = defaultdict(list)

    def record(self, *, bucket: str, detail: str) -> None:
        self.counts[bucket] += 1
        if bucket in REPORTED_BUCKETS:
            self.hits[bucket].append(detail)

    def total(self) -> int:
        return sum(self.counts.values())

    def report(self) -> None:
        print(f"\n{self.label}: {self.total()}")
        for bucket in BUCKETS:
            print(f"  {bucket:14} {self.counts[bucket]}")
        for bucket in REPORTED_BUCKETS:
            print(f"  --- {bucket} ---")
            for detail in self.hits[bucket] or ["(none)"]:
                print(f"    {detail}")


def classify(*, declared: dict[str, set[str]], domain: str, code: str) -> str:
    owners = declared.get(code, set())
    if not owners:
        return "nowhere"
    if owners == {domain}:
        return "own-only"
    if domain in owners:
        return "both"
    return "sibling-only"


def main(roots: list[str]) -> None:
    pipe_tally = Tally(label="bare in-body PIPE refs")
    concept_tally = Tally(label="bare in-body CONCEPT refs")
    units_read = 0
    bundles_read = 0

    for raw_root in roots:
        root = pathlib.Path(raw_root).resolve()
        if not root.is_dir():
            msg = f"root '{raw_root}' is not a directory"
            raise SystemExit(msg)
        by_unit = read_bundles(root)
        units_read += len(by_unit)
        for bundles in (by_unit[unit_dir] for unit_dir in sorted(by_unit)):
            bundles_read += len(bundles)
            declared_pipes: dict[str, set[str]] = defaultdict(set)
            declared_concepts: dict[str, set[str]] = defaultdict(set)
            for bundle in bundles:
                for pipe_code in bundle.pipes:
                    declared_pipes[pipe_code].add(bundle.domain)
                for concept_code in bundle.concepts:
                    declared_concepts[concept_code].add(bundle.domain)

            for bundle in bundles:
                location = bundle.path.relative_to(root) if root in bundle.path.parents else bundle.path
                for pipe_code, pipe_body in bundle.pipes.items():
                    if not isinstance(pipe_body, dict):
                        continue
                    for reference in bare_pipe_references(pipe_body):
                        if "->" in reference.code or "." in reference.code:
                            continue
                        bucket = classify(declared=declared_pipes, domain=bundle.domain, code=reference.code)
                        owners = sorted(declared_pipes.get(reference.code, set()))
                        pipe_tally.record(
                            bucket=bucket,
                            detail=f"{location}: {bundle.domain}.{pipe_code} -> '{reference.code}' declared in {owners}",
                        )
                for reference in bare_concept_references(bundle):
                    code = strip_multiplicity(reference.code)
                    if "->" in code or "." in code or code in NATIVE_CONCEPT_CODES:
                        continue
                    bucket = classify(declared=declared_concepts, domain=bundle.domain, code=code)
                    owners = sorted(declared_concepts.get(code, set()))
                    concept_tally.record(
                        bucket=bucket,
                        detail=f"{location}: {bundle.domain}.{reference.where} -> '{code}' declared in {owners}",
                    )

    print(f"roots: {', '.join(roots)}")
    print(f"merge units: {units_read}")
    print(f"bundles read: {bundles_read}")
    pipe_tally.report()
    concept_tally.report()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
