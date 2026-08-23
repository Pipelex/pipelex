"""Full-bundle parsing of intent hints (spec: intent-hints.md): the three authoring sites land on
their blueprints, hint-free expanded slots collapse, and the rejected probe fails as an unknown
slot-table key.
"""

from pathlib import Path

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint, PipeBlueprint

_DATA_DIR = Path(__file__).parents[3] / "data" / "input_semantics"
_HINTED_BUNDLE_PATH = _DATA_DIR / "hinted_bundle.mthds"
_REJECTED_SLOT_KEY_PATH = _DATA_DIR / "rejected" / "per_input_description.mthds_invalid"


def _parse_hinted_bundle() -> PipelexBundleBlueprint:
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=_HINTED_BUNDLE_PATH)
    assert isinstance(blueprint, PipelexBundleBlueprint)
    return blueprint


def _hinted_concept(blueprint: PipelexBundleBlueprint, code: str) -> ConceptBlueprint:
    assert blueprint.concept is not None
    value = blueprint.concept[code]
    assert isinstance(value, ConceptBlueprint)
    return value


class TestHintedBundleParsing:
    def test_concept_site(self):
        blueprint = _parse_hinted_bundle()
        assert _hinted_concept(blueprint, "Essay").hints == {"intent": "prose"}
        assert _hinted_concept(blueprint, "PlainBadge").hints is None

    def test_structure_field_site(self):
        blueprint = _parse_hinted_bundle()
        review = _hinted_concept(blueprint, "Review")
        assert isinstance(review.structure, dict)
        headline = review.structure["headline"]
        assert isinstance(headline, ConceptStructureBlueprint)
        assert headline.hints == {"intent": "label"}
        stars = review.structure["stars"]
        assert isinstance(stars, ConceptStructureBlueprint)
        assert stars.hints == {"intent": "rating"}
        plain = review.structure["plain"]
        assert isinstance(plain, ConceptStructureBlueprint)
        assert plain.hints is None
        quirk = review.structure["quirk"]
        assert isinstance(quirk, ConceptStructureBlueprint)
        assert quirk.hints == {"emphasis": "HINTED_unknown_value"}

    def test_input_slot_site(self):
        blueprint = _parse_hinted_bundle()
        assert blueprint.pipe is not None
        pipe = blueprint.pipe["hinted_slots"]
        assert isinstance(pipe, PipeBlueprint)
        assert pipe.inputs is not None
        assert pipe.inputs["plain"] == "Essay"
        # The expanded form without hints collapses to the very same string form.
        assert pipe.inputs["expanded_plain"] == "Essay"
        hinted = pipe.inputs["hinted"]
        assert isinstance(hinted, InputSlotBlueprint)
        assert hinted.concept == "Review"
        assert hinted.hints == {"intent": "prose"}
        marked = pipe.inputs["hinted_marked"]
        assert isinstance(marked, InputSlotBlueprint)
        assert marked.concept == "Badge[]"
        assert marked.hints == {"intent": "label"}


class TestRejectedSlotTableKey:
    def test_per_input_description_fails_as_unknown_slot_table_key(self):
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(bundle_path=_REJECTED_SLOT_KEY_PATH)
        assert "extra" in str(exc_info.value).lower()
