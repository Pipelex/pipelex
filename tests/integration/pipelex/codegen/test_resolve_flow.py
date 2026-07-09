import importlib.util
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import tomli
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION

from pipelex.codegen.crate_encoding import encode_crate_json, encode_crate_toml
from pipelex.codegen.emitters.target import CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.hub import get_library_manager
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipeline.execution_seams import load_libraries_and_activate

# A single-package, multi-bundle closure (domain `pipeline` split across two sibling files, no
# cross-package `alias->` refs). `main.mthds` references a concept (`Score`) and a sub-pipe
# (`compute_score`) defined in `steps.mthds`, plus the native `Text` — so the resolve flow must merge,
# qualify cross-file concept/pipe refs, and materialize the native. This is the primary B1 target shape.
MAIN_MTHDS = """\
domain = "pipeline"
description = "Pipeline domain"

[concept.Report]
description = "A report"
structure.score = { description = "the score", type = "concept", concept_ref = "Score" }
structure.label = { description = "a label", type = "concept", concept_ref = "Text" }

[pipe.run_pipeline]
type = "PipeSequence"
description = "Run the pipeline"
inputs = { doc = "Text" }
output = "Score"
steps = [{ pipe = "compute_score", result = "score" }]
"""

STEPS_MTHDS = """\
domain = "pipeline"

[concept.Score]
description = "A score"
structure = { value = { description = "the value", type = "number" } }

[pipe.compute_score]
type = "PipeLLM"
description = "Compute a score"
inputs = { doc = "Text" }
output = "Score"
model = "$quick-reasoning"
prompt = "Compute a score from $doc"
"""


def _structure_field(concept: ConceptBlueprint | str, field_name: str) -> ConceptStructureBlueprint:
    """Narrow a concept's structure field to a `ConceptStructureBlueprint` for typed assertions."""
    assert isinstance(concept, ConceptBlueprint)
    assert isinstance(concept.structure, dict)
    field = concept.structure[field_name]
    assert isinstance(field, ConceptStructureBlueprint)
    return field


class TestResolveFlow:
    """Integration: the resolve pipeline (closure → crate → normalize → encode → round-trip)."""

    def test_multi_bundle_closure_normalizes_and_encodes(self, load_empty_library: Callable[[], str]):
        """A multi-bundle closure resolves to a flat, fully-qualified, natives-expanded crate; both
        encodings carry the same fingerprint; and the TOML form is directly runnable (round-trip load).
        """
        library_manager = get_library_manager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            closure_dir = Path(tmp_dir)
            (closure_dir / "main.mthds").write_text(MAIN_MTHDS, encoding="utf-8")
            (closure_dir / "steps.mthds").write_text(STEPS_MTHDS, encoding="utf-8")

            resolve_library_id = load_libraries_and_activate([closure_dir])
            crate = library_manager.get_crate(resolve_library_id)
            assert crate is not None
            normalized = normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)
            library_manager.teardown(library_id=resolve_library_id)

            # Flat, fully-qualified keyspace across both bundles.
            assert {"pipeline.Report", "pipeline.Score", "pipeline.compute_score", "pipeline.run_pipeline"} <= set(
                normalized.concepts.keys() | normalized.pipes.keys()
            )
            # Native materialized (referenced by a field + pipe io).
            assert "native.Text" in normalized.concepts

            # Cross-file concept ref qualified against the owner domain.
            report = normalized.concepts["pipeline.Report"]
            assert _structure_field(report, "score").concept_ref == "pipeline.Score"
            assert _structure_field(report, "label").concept_ref == "native.Text"

            # Cross-file pipe ref inside the sequence controller qualified against the owner domain.
            run_pipeline = normalized.pipes["pipeline.run_pipeline"]
            assert isinstance(run_pipeline, PipeSequenceBlueprint)
            assert run_pipeline.steps[0].pipe == "pipeline.compute_score"

            # Both encodings agree on the fingerprint.
            json_doc = json.loads(encode_crate_json(normalized))
            toml_doc = tomli.loads(encode_crate_toml(normalized))
            assert json_doc["fingerprint"] == toml_doc["fingerprint"] == normalized.fingerprint

            # Directly runnable: the TOML form parses back into a crate that loads into a live library.
            from_toml = LibraryCrate.model_validate(toml_doc)
            assert from_toml.compute_normalized() == normalized.fingerprint
            reload_library_id = load_empty_library()
            library_manager.load_from_crate(library_id=reload_library_id, crate=from_toml)
            reloaded = library_manager.get_library(library_id=reload_library_id)
            assert "pipeline.run_pipeline" in reloaded.pipe_library.root
            assert "pipeline.Report" in reloaded.concept_library.root

    def test_multi_bundle_closure_feeds_every_emitter(self, tmp_path: Path):
        """The resolved multi-bundle crate projects through every types target, and the emitted Python
        execs into real classes — the resolve -> emit chain end to end (fixture 2).
        """
        library_manager = get_library_manager()
        with tempfile.TemporaryDirectory() as tmp_dir:
            closure_dir = Path(tmp_dir)
            (closure_dir / "main.mthds").write_text(MAIN_MTHDS, encoding="utf-8")
            (closure_dir / "steps.mthds").write_text(STEPS_MTHDS, encoding="utf-8")
            resolve_library_id = load_libraries_and_activate([closure_dir])
            crate = library_manager.get_crate(resolve_library_id)
            assert crate is not None
            normalized = normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)
            library_manager.teardown(library_id=resolve_library_id)

        # ts-zod projects a pure types file and its binder; each Python target projects one module.
        assert {file.filename for file in emit_types(normalized, target=CodegenTarget.TS_ZOD)} == {"types.ts", "binder.ts"}
        for target in (CodegenTarget.PYTHON_STRUCTURES, CodegenTarget.PYTHON_PYDANTIC):
            emitted = emit_types(normalized, target=target)
            assert len(emitted) == 1
            module_name = emitted[0].filename.removesuffix(".py")
            module_path = tmp_path / f"{target.name.lower()}_{emitted[0].filename}"
            module_path.write_text(emitted[0].content, encoding="utf-8")
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            assert spec is not None
            assert spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            # Report cross-references Score (defined in the sibling bundle) — both classes build, and
            # Score, a leaf, instantiates. Report's fields survive the projection.
            assert module.Score(value=1.0).value == 1.0
            assert {"score", "label"} <= set(module.Report.model_fields)
