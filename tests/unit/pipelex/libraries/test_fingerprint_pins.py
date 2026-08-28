"""Pinned-fingerprint regression for the intent-hints milestone (H2).

The spec rule under guard: a library that authors no hints keeps its fingerprint. Both fingerprint
functions hash `model_dump(mode="json")` payloads, so an optional field added carelessly to a
blueprint model lands as `"hints": null` in every dumped concept and field and silently migrates
every existing crate digest. These pins were computed on the models BEFORE the hints fields landed;
they must never move for a hint-free bundle.

If this test fails, do NOT re-pin the hexes — find the field or serializer that leaked a new member
into the dumped payload of a hint-free blueprint and make its absence a dropped key instead.
"""

from pathlib import Path

from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.mthds_parsing.parser import MthdsParser

_PROBE_BUNDLE_PATH = Path(__file__).parents[3] / "data" / "input_semantics" / "probe_bundle.mthds"

# Computed on the probe bundle at the base of feature/Engine-hints (models without hints fields),
# recomputed once on feature/Enrich when the bundle itself changed content: its `titled_default`
# field moved to a rejected/ fixture (E3 outlaws the required+default pair) — a fixture-content
# change, not a model leak, so the recompute is the legitimate exception to the note above.
# The normalized pin was recomputed again when MTHDS v0.9.0 made `native.Html`'s `css_class`
# optional: normalization materializes the pinned natives into the crate, so a standard change to
# a pinned definition legitimately moves every conforming implementation's normalized digest — the
# content pin, which hashes only authored content, did not move.
_PINNED_CONTENT_FINGERPRINT = "053d3ce1a1963feffcea1aaea21e6329a7d2d2371cecdb92eb4a1e51269b0043"
_PINNED_NORMALIZED_FINGERPRINT = "8d6fd88088228beb4f5fdad5b204a30146e8fcfc9392df93caa7df37d4ed471a"

_MTHDS_TEST_VERSION = "0.0.0-test"


class TestHintFreeFingerprintPins:
    def test_content_fingerprint_is_stable(self):
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=_PROBE_BUNDLE_PATH)
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[blueprint])
        assert crate.compute_fingerprint() == _PINNED_CONTENT_FINGERPRINT

    def test_normalized_fingerprint_is_stable(self):
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=_PROBE_BUNDLE_PATH)
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[blueprint])
        normalized = normalize_crate(crate, mthds_version=_MTHDS_TEST_VERSION)
        assert normalized.compute_normalized() == _PINNED_NORMALIZED_FINGERPRINT
