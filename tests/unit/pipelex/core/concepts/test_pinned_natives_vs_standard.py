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
- **Absence is named, never silently passed over.** Without the sibling checkout the comparisons
  against the page skip with the reason below — kept so a contributor does not need the whole
  workspace to run the suite. It is not an opt-out: the `MTHDS standard conformance` workflow
  checks the standard out beside this repo and runs this module on every pull request, so a
  disagreement with the page fails the merge either way.

`PINNED_NATIVES_MTHDS_VERSION` — the number naming *which* set this is — is held here too, and by
two different authorities, because a value nothing reads is a value that goes stale in silence (it
sat at `1.0.0` across the standard's `2.0.0` cut, and no test in this repo could say so). The page
pins the number and is compared against it below; the installed `mthds` says which standard version
this engine implements, and that comparison needs no checkout, so it runs for every contributor.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.pinned_blueprints import PINNED_NATIVES_MTHDS_VERSION, make_pinned_native_blueprint
from pipelex.tools.misc.semver import parse_version

# This repo and the standard's repo as siblings — the documented workspace layout, reproduced on
# CI runners by the `MTHDS standard conformance` workflow's double checkout.
_REPO_ROOT = Path(__file__).resolve().parents[5]
SPEC_PAGE = _REPO_ROOT.parent / "mthds" / "docs" / "spec" / "native-concepts.md"

_NEEDS_THE_PAGE = pytest.mark.skipif(
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


def read_spec_pinned_version() -> str:
    """The standard version the page says the set below it was pinned at.

    The page states it twice — once in prose ("The set below was pinned at MTHDS `2.0.0`") and once
    in the heading that opens the set ("The Pinned Set — Pinned at MTHDS 2.0.0"). Both spellings are
    collected and required to agree, so a half-done re-pinning on the page is a failure here rather
    than a coin toss over which sentence this reader happened to match.
    """
    statements: list[str] = re.findall(r"[Pp]inned at MTHDS\s+`?(\d+\.\d+\.\d+)`?", SPEC_PAGE.read_text(encoding="utf-8"))
    assert statements, "the standard's page no longer states the version its native set is pinned at"
    assert len(set(statements)) == 1, f"the standard's page states more than one pinned version for its native set: {sorted(set(statements))}"
    return statements[0]


class TestPinnedNativesAgreeWithTheStandard:
    pytestmark = _NEEDS_THE_PAGE

    def test_names_the_version_the_page_pins_the_set_at(self):
        """The set is a copy; `PINNED_NATIVES_MTHDS_VERSION` is the label on it, and a mislabelled copy misleads.

        Nothing inside this package reads the constant, so a wrong value breaks nothing here — it
        misleads whoever reads it as the answer to "which pinned set is this", which is what its
        name promises, and a downstream port that reports it as this reference's natives version
        then gates its own goldens against a dead number.
        """
        assert read_spec_pinned_version() == PINNED_NATIVES_MTHDS_VERSION, (
            f"PINNED_NATIVES_MTHDS_VERSION says {PINNED_NATIVES_MTHDS_VERSION!r} but the standard's page pins the set at "
            f"{read_spec_pinned_version()!r} — {_DISAGREEMENT_REMEDY}"
        )

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


class TestPinnedNativesVersionAgreesWithTheEngine:
    """The one comparison that needs no sibling checkout: the label against the standard this engine implements."""

    def test_pinned_set_is_not_from_a_standard_version_this_engine_does_not_implement(self):
        """An implementation of standard version `V` materializes the greatest pinned set not above `V`.

        This module holds exactly one pinned set, so the rule reduces to a bound: the set it holds
        cannot have been pinned by a standard version later than the one the installed `mthds`
        implements. A pin bump that moves the standard backwards, or a re-pinning transcribed here
        ahead of the `mthds` bump that carries it, fails this without needing the page.
        """
        assert parse_version(PINNED_NATIVES_MTHDS_VERSION) <= parse_version(MTHDS_STANDARD_VERSION), (
            f"the pinned native set is labelled {PINNED_NATIVES_MTHDS_VERSION!r}, later than the standard version this "
            f"engine implements ({MTHDS_STANDARD_VERSION!r}) — this engine cannot materialize a set pinned in the future"
        )
