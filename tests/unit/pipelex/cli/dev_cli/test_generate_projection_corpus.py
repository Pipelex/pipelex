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
- **A pipe with no inputs is captured from the projection alone.** An empty input form is a valid
  form, but the engine's own renderer refuses one, so the capture takes the projected half and skips
  the comparison. No corpus bundle declares such a pipe, so the case is put to the generator here.
- **Every template the shaper refuses is exactly one the registry declares.** The templates are
  pinned to be filled in and handed back to the runtime, so the capture round-trips each one through
  `InputShaper.shape`. This is where that round-trip actually runs, against real descriptors and the
  real concept library, and states that its verdicts meet `EXPECTED_UNSHAPEABLE` on the nose.

The two gates that measure the capture are checked at their own collectors, in
`test_projection_divergence_gate.py` and `test_projection_shaping_gate.py`: the corpus is exactly the
case where the projection is right, so nothing here can state what happens when it is wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.generate_projection_corpus_cmd import (
    ENGINE_DIR_NAME,
    EXPECTED_UNSHAPEABLE,
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

# A pipe declaring no inputs at all, which no corpus bundle does: the descriptor is the empty form
# and the projection renders it as `{}`, while the engine's renderer raises NoInputsRequiredError.
NO_INPUT_BUNDLE = """domain      = "no_input_probe"
description = "A throwaway bundle whose only pipe declares no inputs at all"
main_pipe   = "no_input_pipe"

[pipe.no_input_pipe]
type        = "PipeLLM"
description = "A pipe that takes no inputs, so its input form is the empty one"
output      = "Text"
prompt      = \"\"\"
Write a haiku about an empty form.
\"\"\"
"""

NO_INPUT_PIPE_REF = "no_input_probe.no_input_pipe"


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

    async def test_every_unshapeable_template_is_one_the_registry_declares(self, tmp_path: Path) -> None:
        """The round-trip runs for real here, so the registry is measured rather than restated."""
        manifest = await generate_projection_corpus(bundle_paths=CORPUS_BUNDLES, output_dir=tmp_path)

        # Exactly the declared set, in both directions: an undeclared refusal fails the capture, and
        # a declaration whose gap closed fails it too. Stating it here is what makes the registry a
        # measurement of the corpus rather than a list somebody keeps in their head.
        assert {(entry.pipe_ref, entry.shape): entry.ledger_item for entry in manifest.unshapeable} == EXPECTED_UNSHAPEABLE

        for entry in manifest.unshapeable:
            assert entry.pipe_ref in manifest.pipes
            assert entry.shape in manifest.shapes
            # The error class is contract-stable and belongs in the committed bytes; which class it
            # is today is not asserted, because typing the explicit arm's escaped pydantic error
            # (L-260831-1e1a71) will change it without changing anything this corpus pins.
            assert entry.error_type

        # The gap is a descriptor one, so it takes both shapes of the pipes it touches.
        assert {entry.shape for entry in manifest.unshapeable} == set(manifest.shapes)

    async def test_a_rerun_writes_the_same_bytes(self, tmp_path: Path) -> None:
        """The corpus is committed, so the capture has to be a function of the bundles alone."""
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"

        await generate_projection_corpus(bundle_paths=CORPUS_BUNDLES, output_dir=first_dir)
        await generate_projection_corpus(bundle_paths=CORPUS_BUNDLES, output_dir=second_dir)

        assert _corpus_files(corpus_dir=first_dir) == _corpus_files(corpus_dir=second_dir)

    async def test_a_pipe_with_no_inputs_is_captured_from_the_projection_alone(self, tmp_path: Path) -> None:
        """`PipeInputFormDescriptor` documents `{"fields": []}` as valid; only the engine refuses one."""
        bundle_path = tmp_path / "no_input_bundle.mthds"
        bundle_path.write_text(NO_INPUT_BUNDLE, encoding="utf-8")
        output_dir = tmp_path / "corpus"

        manifest = await generate_projection_corpus(bundle_paths=[*CORPUS_BUNDLES, bundle_path], output_dir=output_dir)

        assert NO_INPUT_PIPE_REF in manifest.pipes
        templates_dir = output_dir / TEMPLATES_DIR_NAME
        for shape in manifest.shapes:
            # The template is the empty object; its TOML rendering is the empty document, which is
            # the only way TOML has to say it.
            assert (templates_dir / f"{NO_INPUT_PIPE_REF}.{shape}.json").read_text(encoding="utf-8") == "{}"
            assert (templates_dir / f"{NO_INPUT_PIPE_REF}.{shape}.toml").read_text(encoding="utf-8") == ""
        assert not list((output_dir / ENGINE_DIR_NAME).glob(f"{NO_INPUT_PIPE_REF}.*"))
