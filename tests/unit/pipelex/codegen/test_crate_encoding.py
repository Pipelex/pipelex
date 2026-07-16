import json

import tomli

from pipelex.codegen.crate_encoding import CrateEncoding, encode_crate, encode_crate_json, encode_crate_toml
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

MTHDS_TEST_VERSION = "0.1.0-test"


def _normalized_crate() -> LibraryCrate:
    """A small normalized crate (natives expanded, refs qualified) to encode."""
    crate = LibraryCrate(
        concepts={
            "scoring.Score": ConceptBlueprint(
                description="A weighted score",
                structure={
                    "value": ConceptStructureBlueprint(description="the value", type=ConceptStructureBlueprintFieldType.NUMBER),
                    "note": ConceptStructureBlueprint(description="a note", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Text"),
                },
            ),
        },
        pipes={
            "scoring.compute": PipeLLMBlueprint(description="Compute", inputs={"data": "Text"}, output="Score", prompt="from $data"),
        },
        domains={"scoring": DomainBlueprint(code="scoring", description="Scoring domain")},
        source_map={"scoring.Score": "/fake/scoring.mthds"},
    )
    return normalize_crate(crate, mthds_version=MTHDS_TEST_VERSION)


class TestCrateEncoding:
    """Unit tests for the JSON and TOML crate encodings."""

    def test_both_encodings_carry_the_crate_fingerprint(self):
        """The fingerprint is a property of the logical crate; both encodings emit the same one."""
        crate = _normalized_crate()
        json_doc = json.loads(encode_crate_json(crate))
        toml_doc = tomli.loads(encode_crate_toml(crate))
        assert json_doc["fingerprint"] == crate.fingerprint
        assert toml_doc["fingerprint"] == crate.fingerprint

    def test_both_encodings_round_trip_to_the_same_logical_crate(self):
        """Parsing either encoding back into a LibraryCrate recomputes the same fingerprint and content."""
        crate = _normalized_crate()
        from_json = LibraryCrate.model_validate(json.loads(encode_crate_json(crate)))
        from_toml = LibraryCrate.model_validate(tomli.loads(encode_crate_toml(crate)))
        assert from_json.compute_normalized() == crate.fingerprint
        assert from_toml.compute_normalized() == crate.fingerprint
        assert from_json.concepts == from_toml.concepts
        assert from_json.pipes == from_toml.pipes
        assert from_json.domains == from_toml.domains

    def test_toml_quotes_dotted_qualified_keys(self):
        """Dotted qualified refs are emitted as quoted single keys, never unquoted nested tables."""
        toml_text = encode_crate_toml(_normalized_crate())
        assert '[concepts."scoring.Score"]' in toml_text
        assert '[concepts."native.Text"]' in toml_text
        assert '[pipes."scoring.compute"]' in toml_text
        # An unquoted dotted header would be silently parsed as nested tables — must never appear.
        assert "[concepts.scoring.Score]" not in toml_text

    def test_provenance_source_and_pipe_category_are_excluded(self):
        """Inline `source` and the internal `pipe_category` are dropped; top-level `source_map` stays."""
        payload = json.loads(encode_crate_json(_normalized_crate()))
        assert "source" not in payload["concepts"]["scoring.Score"]
        assert "source" not in payload["pipes"]["scoring.compute"]
        assert "pipe_category" not in payload["pipes"]["scoring.compute"]
        assert payload["source_map"] == {"scoring.Score": "/fake/scoring.mthds"}

    def test_top_level_maps_are_key_sorted(self):
        """Concepts/pipes/domains are emitted in sorted key order for minimal, stable diffs."""
        payload = json.loads(encode_crate_json(_normalized_crate()))
        assert list(payload["concepts"].keys()) == sorted(payload["concepts"].keys())

    def test_encode_crate_dispatch_matches_direct_encoders(self):
        """`encode_crate` dispatches to the encoding-specific encoder for each `CrateEncoding`."""
        crate = _normalized_crate()
        assert encode_crate(crate, encoding=CrateEncoding.JSON) == encode_crate_json(crate)
        assert encode_crate(crate, encoding=CrateEncoding.TOML) == encode_crate_toml(crate)
