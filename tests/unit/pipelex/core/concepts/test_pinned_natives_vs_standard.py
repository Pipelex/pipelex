"""The pinned native-concept set, held against the standard's own page.

`pipelex/core/concepts/native/pinned_blueprints.py` is a *copy* — the MTHDS standard pins the
normative definitions in `mthds/docs/spec/native-concepts.md`, and a copy that nothing compares is
a copy that drifts. Drift here is not cosmetic: the materialized natives are hashed into a crate's
fingerprint, so one reworded field description gives two conforming producers two different digests
for the same library. The consistency probe in `tests/unit/pipelex/codegen/test_native_expansion.py`
compares this repo's two copies (the pinned set and the runtime content classes) to *each other*;
this module is the missing third leg — the comparison against the authority both answer to.

The page is read live from the sibling `mthds/` checkout, at whatever state that checkout is in —
deliberately unpinned, because the standard is the authority this implementation answers to, and
reading a pinned copy would only re-assert that two files this repo controls still match. Two
consequences follow, both by design:

- **A red here can arrive with no pipelex commit involved.** When the standard ships a definition
  change, this check goes red on every PR until the pinned set catches up. That red means "the
  standard moved" — it is not the PR's fault, and the remedy is a dedicated change bringing
  `pinned_blueprints.py` (and the matching runtime content class) to the page, never a tweak to
  whatever PR happened to be open.
- **Absence is named, never silently passed over.** Without the sibling checkout the module skips
  with the reason below — kept so a contributor does not need the whole workspace to run the
  suite. It is not an opt-out: the `MTHDS standard conformance` workflow checks the standard out
  beside this repo and runs this module on every pull request, so a disagreement with the page
  fails the merge either way.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.pinned_blueprints import make_pinned_native_blueprint

# This repo and the standard's repo as siblings — the documented workspace layout, reproduced on
# CI runners by the `MTHDS standard conformance` workflow's double checkout.
_REPO_ROOT = Path(__file__).resolve().parents[5]
SPEC_PAGE = _REPO_ROOT.parent / "mthds" / "docs" / "spec" / "native-concepts.md"

pytestmark = pytest.mark.skipif(
    not SPEC_PAGE.exists(),
    reason=(
        "needs the standard's own repository checked out at ../mthds — without it the pinned set is compared "
        "against nothing here (the codegen consistency probe still runs, and the 'MTHDS standard conformance' "
        "CI workflow runs this module against a fresh checkout on every pull request)"
    ),
)

_DISAGREEMENT_REMEDY = (
    "if this change did not touch the pinned set, the MTHDS standard moved and this repo is behind it — "
    "that red is not this PR's fault; bring pinned_blueprints.py and the matching runtime content class "
    "to the page in a dedicated change"
)


def read_spec_definitions() -> list[tuple[str, dict[str, Any]]]:
    """The `### native.<Code>` definitions, read out of the spec page's fenced TOML blocks.

    Every fenced `toml` block on that page is one definition, written as an author would write the
    concept — the same structure language the pinned set is authored in, so the comparison below is
    a plain deep equality rather than a projection. Returned as a list so section *order* is
    comparable too.
    """
    page = SPEC_PAGE.read_text(encoding="utf-8")
    definitions: list[tuple[str, dict[str, Any]]] = []
    for block in re.findall(r"```toml\n(.*?)```", page, flags=re.DOTALL):
        table = tomllib.loads(block)
        for code, definition in table.get("concept", {}).items():
            definitions.append((code, definition))
    return definitions


class TestPinnedNativesAgreeWithTheStandard:
    def test_pins_the_same_natives_in_the_pages_own_section_order(self):
        page_codes = [code for code, _ in read_spec_definitions()]
        assert page_codes == [code.value for code in NativeConceptCode], (
            f"the standard's page and this repo's pinned set disagree on which natives exist, or in what order — {_DISAGREEMENT_REMEDY}"
        )

    @pytest.mark.parametrize("native_code", list(NativeConceptCode))
    def test_transcribes_the_definition_exactly_as_the_page_states_it(self, native_code: NativeConceptCode):
        """Deep equality, definition for definition and field for field, descriptions included.

        The page's authored TOML parses into the same `ConceptBlueprint` model the pinned set is
        built from, so one comparison covers every member — a field added, a type changed, a
        `required` flipped, a description reworded — and the model's closed shape (extra="forbid")
        makes a member it does not know a loud failure rather than a silent drop.
        """
        page_definition = dict(read_spec_definitions()).get(native_code.value)
        assert page_definition is not None, f"the page has no definition for native.{native_code.value}"
        assert make_pinned_native_blueprint(native_code) == ConceptBlueprint.model_validate(page_definition), (
            f"native.{native_code.value}: the pinned blueprint disagrees with the standard's page — {_DISAGREEMENT_REMEDY}"
        )

    @pytest.mark.parametrize("native_code", list(NativeConceptCode))
    def test_keeps_the_structure_fields_in_the_pages_order(self, native_code: NativeConceptCode):
        """Field order is normative (it governs the crate's emitted encodings), and dict equality cannot see it."""
        page_definition: dict[str, Any] = dict(read_spec_definitions()).get(native_code.value) or {}
        page_structure: dict[str, Any] = page_definition.get("structure") or {}
        pinned_structure = make_pinned_native_blueprint(native_code).structure
        pinned_keys = list(pinned_structure.keys()) if isinstance(pinned_structure, dict) else []
        assert pinned_keys == list(page_structure.keys()), (
            f"native.{native_code.value}: the pinned structure's field order disagrees with the page — {_DISAGREEMENT_REMEDY}"
        )
