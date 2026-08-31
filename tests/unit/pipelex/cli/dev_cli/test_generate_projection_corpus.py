"""The corpus generator produces a complete, stable capture, and every divergence it declares is real.

The generator is the sole producer of the shared projection fixture corpus committed in
`mthds-js/tests/fixtures/protocol/` and `mthds-python/tests/fixtures/protocol/`. Two properties make
that corpus trustworthy, and both are checked here against the corpus bundles themselves:

- **Every declared divergence occurs.** A class declared but no longer produced would leave the
  manifest claiming a difference from the engine that no longer exists, and every consumer repo's
  lapse check reads that manifest. The generator raises on a lapse; this states it as a property.
- **A rerun writes the same bytes.** The corpus is committed, so a capture that varied run to run
  would show up as a diff nobody authored — and the enum placeholder is exactly where the engine's
  own renderer varies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.generate_projection_corpus_cmd import (
    ENGINE_DIR_NAME,
    INPUT_FORM_FILE_NAME,
    MANIFEST_FILE_NAME,
    PIPE_IO_CONTRACTS_FILE_NAME,
    TEMPLATES_DIR_NAME,
    CorpusManifest,
    generate_projection_corpus,
)

CORPUS_BUNDLES = [
    Path("tests/data/input_semantics/hinted_bundle.mthds"),
    Path("tests/data/input_semantics/probe_bundle.mthds"),
    Path("tests/data/input_semantics/scaffold_bundle.mthds"),
]


def _corpus_files(*, corpus_dir: Path) -> dict[str, str]:
    """Every committed file in the corpus, by path relative to its root — the engine's copies excluded."""
    return {
        str(path.relative_to(corpus_dir)): path.read_text(encoding="utf-8")
        for path in sorted(corpus_dir.rglob("*"))
        if path.is_file() and ENGINE_DIR_NAME not in path.relative_to(corpus_dir).parts
    }


@pytest.mark.asyncio(loop_scope="class")
class TestGenerateProjectionCorpus:
    async def test_the_corpus_is_complete_and_its_divergences_are_all_real(self, tmp_path: Path) -> None:
        """One capture, checked for the two things a consumer repo cannot check for itself."""
        manifest = await generate_projection_corpus(bundle_paths=CORPUS_BUNDLES, output_dir=tmp_path)

        # Every declared divergence is non-vacuous: it names sites, and each states a value the
        # engine emits and a different one the corpus expects.
        assert manifest.divergences
        for divergence in manifest.divergences:
            assert divergence.examples, f"divergence {divergence.divergence_id} declares no site"
            assert divergence.reason
            for example in divergence.examples:
                assert example.engine != example.expected

        # Every pipe is captured in both shapes and both formats, and nothing is empty.
        template_dir = tmp_path / TEMPLATES_DIR_NAME
        expected_files = {
            f"{pipe_ref}.{shape}.{file_format}" for pipe_ref in manifest.pipes for shape in manifest.shapes for file_format in manifest.formats
        }
        written = {path.name for path in template_dir.iterdir() if path.name != MANIFEST_FILE_NAME}
        assert written == expected_files
        for path in template_dir.iterdir():
            assert path.read_text(encoding="utf-8").strip(), f"{path.name} is empty"

        # The descriptor half is captured beside the templates: a projection needs both.
        assert json.loads((tmp_path / INPUT_FORM_FILE_NAME).read_text(encoding="utf-8")).keys() == set(manifest.pipes)
        assert json.loads((tmp_path / PIPE_IO_CONTRACTS_FILE_NAME).read_text(encoding="utf-8")).keys() == set(manifest.pipes)

        # The manifest round-trips: it is what the consumer repos parse.
        assert CorpusManifest.model_validate_json((template_dir / MANIFEST_FILE_NAME).read_text(encoding="utf-8")) == manifest

    async def test_a_rerun_writes_the_same_bytes(self, tmp_path: Path) -> None:
        """The corpus is committed, so the capture has to be a function of the bundles alone."""
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"

        await generate_projection_corpus(bundle_paths=CORPUS_BUNDLES, output_dir=first_dir)
        await generate_projection_corpus(bundle_paths=CORPUS_BUNDLES, output_dir=second_dir)

        assert _corpus_files(corpus_dir=first_dir) == _corpus_files(corpus_dir=second_dir)
