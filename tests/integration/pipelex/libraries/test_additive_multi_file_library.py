"""End-to-end proof of the additive multi-file library model.

A same-domain method is authored as separate, additive `.mthds` files (a forward-declared header +
a separate definition) sharing a non-native concept. This composes the two merge-time rules:

- Part A — a `PipeSignature` header and its concrete definition reconcile (the concrete wins).
- Part B / Finding #1 — a same-domain concept declared in one file resolves when referenced by bare
  code from a sibling file, whether loaded in the same directory batch or across separate batches
  (a `-L` library directory).

A native-only contract would pass even with the cross-file bug present, so the shared concept here
(`KeyFinding`) is deliberately non-native.
"""

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle, validate_bundles_from_directory

RESEARCH_CONCEPTS = """
domain = "research"
description = "Research method domain"

[concept]
KeyFinding = "A key finding extracted from a source document"
"""

# Forward-declared header (signature) + a controller referencing it by bare code. Both the
# signature output and the controller output use the non-native concept KeyFinding, declared in
# RESEARCH_CONCEPTS (a sibling file).
RESEARCH_HEADER = """
domain = "research"
description = "Research method headers"

[pipe.find_key_findings]
type = "PipeSignature"
description = "Find the key findings in a document (contract only)."
inputs = { doc = "Text" }
output = "KeyFinding"

[pipe.research_brief]
type = "PipeSequence"
description = "Produce a research brief from a document."
inputs = { doc = "Text" }
output = "KeyFinding"
steps = [
  { pipe = "find_key_findings", result = "findings" },
]
"""

# The concrete definition of find_key_findings, with a contract matching the header.
RESEARCH_DEFINITIONS = """
domain = "research"
description = "Research method definitions"

[pipe.find_key_findings]
type = "PipeLLM"
description = "Find the key findings in a document."
inputs = { doc = "Text" }
output = "KeyFinding"
model = "$quick-reasoning"
prompt = "List the key findings in $doc."
"""

# A self-contained root pipe that references KeyFinding by bare code. Used with a -L library
# directory that declares KeyFinding in a separate load batch.
RESEARCH_ROOT_BARE = """
domain = "research"
description = "Research root referencing a library concept by bare code"

[pipe.extract_finding]
type = "PipeLLM"
description = "Extract a key finding from a document."
inputs = { doc = "Text" }
output = "KeyFinding"
model = "$quick-reasoning"
prompt = "Extract a key finding from $doc."
"""

# A root pipe referencing a concept declared in no file, to prove the error surfaces cleanly.
RESEARCH_ROOT_UNDECLARED = """
domain = "research"
description = "Research root referencing an undeclared concept"

[pipe.extract_ghost]
type = "PipeLLM"
description = "Extract a ghost from a document."
inputs = { doc = "Text" }
output = "Ghost"
model = "$quick-reasoning"
prompt = "Extract a ghost from $doc."
"""


@pytest.mark.asyncio(loop_scope="class")
class TestAdditiveMultiFileLibrary:
    async def test_lenient_validation_passes_with_signature_only(self, load_empty_library: Callable[[], str]):
        """With only the header (no definition), lenient validation passes and find_key_findings stays a signature."""
        load_empty_library()
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            (directory / "concepts.mthds").write_text(RESEARCH_CONCEPTS, encoding="utf-8")
            (directory / "header.mthds").write_text(RESEARCH_HEADER, encoding="utf-8")
            result = await validate_bundles_from_directory(directory=directory, allow_signatures=True)

        pipe_codes = {pipe.code for pipe in result.pipes}
        assert "find_key_findings" in pipe_codes
        assert "research_brief" in pipe_codes
        find_key_findings = next(pipe for pipe in result.pipes if pipe.code == "find_key_findings")
        assert find_key_findings.is_signature
        # The unimplemented header is reported library-wide as a pending signature.
        assert result.pending_signatures == ["research.find_key_findings"]

    async def test_strict_validation_passes_with_definition_and_concrete_wins(self, load_empty_library: Callable[[], str]):
        """Adding the definition lets strict validation pass; the concrete pipe replaces the signature."""
        load_empty_library()
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            (directory / "concepts.mthds").write_text(RESEARCH_CONCEPTS, encoding="utf-8")
            (directory / "header.mthds").write_text(RESEARCH_HEADER, encoding="utf-8")
            (directory / "definitions.mthds").write_text(RESEARCH_DEFINITIONS, encoding="utf-8")
            result = await validate_bundles_from_directory(directory=directory, allow_signatures=False)

        find_key_findings = next((pipe for pipe in result.pipes if pipe.code == "find_key_findings"), None)
        assert find_key_findings is not None
        assert not find_key_findings.is_signature
        # With every header now satisfied by a concrete definition, nothing remains pending.
        assert result.pending_signatures == []

    async def test_cross_batch_bare_concept_reference_via_library_dir(self, load_empty_library: Callable[[], str]):
        """A root pipe references, by bare code, a concept declared in a -L library directory loaded in a separate batch."""
        load_empty_library()
        with tempfile.TemporaryDirectory() as lib_dir:
            (Path(lib_dir) / "concepts.mthds").write_text(RESEARCH_CONCEPTS, encoding="utf-8")
            result = await validate_bundle(
                mthds_contents=[RESEARCH_ROOT_BARE],
                library_dirs=[Path(lib_dir)],
                allow_signatures=False,
            )
        assert "extract_finding" in {pipe.code for pipe in result.pipes}

    async def test_undeclared_concept_surfaces_clean_validate_bundle_error(self, load_empty_library: Callable[[], str]):
        """An undeclared concept reference surfaces as a structured ValidateBundleError, not a raw ConceptLibraryError."""
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[RESEARCH_ROOT_UNDECLARED], library_dirs=[])
        assert "Ghost" in exc_info.value.message
