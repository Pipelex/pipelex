"""Error-surfacing cases for the additive multi-file library model.

The positive end-to-end scenarios (signature/definition reconciliation, cross-file bare/qualified
references, cross-batch concept resolution) live as real on-disk `.mthds` bundles under
``tests/e2e/pipelex/pipes/additive_multi_file_library/``. This module keeps the negative cases —
malformed inputs that must surface a structured ``ValidateBundleError`` rather than a raw traceback
— authored as in-memory strings, since a genuinely-broken bundle has no business sitting on disk.

The shared concept (`KeyFinding`) is deliberately non-native: a native-only contract would pass even
with the cross-file resolution bug present, so it would not prove anything.
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

# A controller referencing a qualified same-domain pipe declared in no file, to prove the missing
# reference still surfaces cleanly once per-file pipe validation no longer fires.
RESEARCH_CONTROLLER_QUALIFIED_MISSING = """
domain = "research"
description = "Research brief controller referencing an undeclared qualified pipe"

[pipe.research_brief]
type = "PipeSequence"
description = "Produce a research brief from a document."
inputs = { doc = "Text" }
output = "KeyFinding"
steps = [
  { pipe = "research.totally_missing", result = "findings" },
]
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
class TestAdditiveMultiFileLibraryErrors:
    async def test_undeclared_concept_surfaces_clean_validate_bundle_error(self, load_empty_library: Callable[[], str]):
        """An undeclared concept reference surfaces as a structured ValidateBundleError, not a raw ConceptLibraryError."""
        load_empty_library()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[RESEARCH_ROOT_UNDECLARED], library_dirs=[])
        assert "Ghost" in exc_info.value.message

    async def test_undeclared_qualified_pipe_ref_surfaces_clean_error(self, load_empty_library: Callable[[], str]):
        """A qualified same-domain step ref to a pipe declared in no file surfaces a clean ValidateBundleError."""
        load_empty_library()
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            (directory / "concepts.mthds").write_text(RESEARCH_CONCEPTS, encoding="utf-8")
            (directory / "controller.mthds").write_text(RESEARCH_CONTROLLER_QUALIFIED_MISSING, encoding="utf-8")
            with pytest.raises(ValidateBundleError, match="totally_missing"):
                await validate_bundles_from_directory(directory=directory, allow_signatures=False)
