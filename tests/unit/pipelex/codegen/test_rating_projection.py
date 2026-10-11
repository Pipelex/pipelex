"""A method whose output is `Rating`: the generated Python and TypeScript carry the level's `label`.

Codegen never reads the runtime content class: normalization materializes the pinned `native.Rating`
into the crate, and every emitter projects that definition. So the member the standard re-pinned at
MTHDS 5.0.0 reaches a consumer's types through the pinned set alone, and this module holds the
projections to it from an authored method, the way a consumer's `pipelex codegen` reaches them:
`python-pydantic` and `ts-zod` emit the native as a model of its own, and `python-structures` points
at the runtime `RatingContent`, which carries the member itself.
"""

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from typing import Any

from pipelex.codegen.emitters.python_pydantic import emit_python_pydantic
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.emitters.ts_zod import emit_ts_zod
from pipelex.codegen.resolved_concepts import ResolvedLibrary, resolve_concepts_from_crate
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.mthds_parsing.parser import MthdsParser
from tests.helpers.ts_toolchain import resolve_node, resolve_zod_package
from tests.unit.pipelex.codegen.conftest import CRATE_TEST_VERSION, load_generated_module

_RATING_METHOD_MTHDS = """
domain = "triage"
description = "Rates how severe a reported issue is"

[concept.Assessment]
description = "An assessment holding a rating as a field"

[concept.Assessment.structure]
severity = { type = "concept", concept_ref = "native.Rating", description = "How severe the issue is", required = true }

[pipe.rate_severity]
type = "PipeLLM"
description = "Rates how severe a reported issue is"
inputs = { report = "Text" }
output = "Rating"
prompt = "How severe is this issue? $report"

[pipe.assess]
type = "PipeLLM"
description = "Assesses a reported issue"
inputs = { report = "Text" }
output = "Assessment"
prompt = "Assess this issue. $report"
"""


def _resolved_rating_method() -> ResolvedLibrary:
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_RATING_METHOD_MTHDS)
    crate = LibraryCrateFactory.make_from_blueprints(blueprints=[blueprint])
    return resolve_concepts_from_crate(normalize_crate(crate, mthds_version=CRATE_TEST_VERSION))


class TestRatingProjection:
    def test_the_crate_materializes_the_rating_with_its_label(self):
        resolved = _resolved_rating_method()
        rating = resolved.by_ref().get("native.Rating")
        assert rating is not None, "a method whose output is Rating must materialize native.Rating into its crate"
        assert [field.name for field in rating.fields] == ["level", "label", "confidence", "probabilities", "position"]

    def test_python_pydantic_carries_the_label(self, tmp_path: Path):
        content = emit_python_pydantic(_resolved_rating_method())[0].content
        assert "class Rating(BaseModel):" in content
        assert "label: str | None" in content
        module = load_generated_module(content, tmp_path=tmp_path, name="gen_models_rating")
        rating = module.Rating(level=1, label="Workaround available")
        assert module.Rating.model_validate(rating.model_dump(mode="json")) == rating
        # The runtime's own transport dump of a labelled rating validates against the generated model.
        wire = RatingContent(level=1, label="Workaround available", confidence=0.6).smart_dump()
        assert module.Rating.model_validate(wire).label == "Workaround available"

    def test_python_structures_points_at_the_runtime_class_that_carries_the_label(self):
        content = emit_python_structures(_resolved_rating_method())[0].content
        assert "severity: RatingContent" in content
        assert "label" in RatingContent.model_fields

    def test_ts_zod_carries_the_label(self):
        content = emit_ts_zod(_resolved_rating_method())[0].content
        assert "export const RatingSchema = z.object({" in content
        assert "label: z.string().nullish()," in content

    def test_the_emitted_schema_parses_the_runtime_payload(self, tmp_path: Path):
        """A real zod, the emitted schema, the runtime's own JSON for a labelled and an unlabelled rating.

        Mandatory under `make test-ts-gates`, as every TypeScript gate is; opportunistic elsewhere, where the
        two pins above hold the line.
        """
        node = resolve_node()
        zod_package = resolve_zod_package()

        content = emit_ts_zod(_resolved_rating_method())[0].content
        wire_payloads: list[dict[str, Any]] = [
            RatingContent(level=1, label="Workaround available", confidence=0.6).smart_dump(),
            RatingContent(level=2).smart_dump(),
        ]
        (tmp_path / "types.ts").write_text(content, encoding="utf-8")
        (tmp_path / "package.json").write_text('{ "type": "module" }\n', encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "zod").symlink_to(zod_package, target_is_directory=True)
        (tmp_path / "wire.json").write_text(json.dumps(wire_payloads), encoding="utf-8")
        (tmp_path / "driver.ts").write_text(
            'import { readFileSync } from "node:fs";\n'
            'import { RatingSchema } from "./types.ts";\n'
            'const wire = JSON.parse(readFileSync("wire.json", "utf-8"));\n'
            "process.stdout.write(JSON.stringify(wire.map((one: unknown) => RatingSchema.parse(one))));\n",
            encoding="utf-8",
        )

        run = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [node, "--experimental-strip-types", "--no-warnings", "driver.ts"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.returncode == 0, f"the emitted schema rejected the runtime's own payload:\n{run.stdout}\n{run.stderr}"

        labelled, unlabelled = json.loads(run.stdout)
        assert labelled["label"] == "Workaround available"
        assert unlabelled["label"] is None
