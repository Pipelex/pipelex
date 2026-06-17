"""End-to-end proof of a top-down recursive-refinement bundle, backed by real on-disk `.mthds` files.

This is the artifact the `mthds-vibe` skill builds: a same-domain library where the `main_pipe` is a
controller and its sub-pipes are forward-declared as signatures, with every concrete definition added
as a separate sibling file. Signatures and concretes reconcile at TWO levels:

    bundle.mthds                -> main_pipe `write_research_brief` as a PipeSignature (the whole job)
    write_research_brief.mthds  -> concrete PipeSequence (satisfies the root header) that forward-declares
                                   `find_key_findings` + `draft_brief` as signatures, owns `KeyFinding`
    find_key_findings.mthds     -> concrete PipeLLM (satisfies the controller's header)
    draft_brief.mthds           -> concrete PipeLLM (satisfies the controller's header)

So `write_research_brief` appears as a signature in one file and a concrete in another; each sub-pipe
likewise. After the additive merge the concretes win at every level and the bundle is runnable.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipeline.validate_bundle import validate_bundles_from_directory

_BUNDLE_DIR = Path(__file__).parent / "recursive_refinement"


@pytest.mark.asyncio(loop_scope="class")
class TestRecursiveRefinementBundle:
    async def test_assembled_bundle_is_runnable_with_concretes_at_every_level(self, load_empty_library: Callable[[], str]):
        """Strict validation passes: nothing is left pending, and the concrete pipe wins at every level
        — the controller `main_pipe` over its `find_key_findings` / `draft_brief` signatures.
        """
        load_empty_library()
        result = await validate_bundles_from_directory(directory=_BUNDLE_DIR, allow_signatures=False)

        pipes_by_code = {pipe.code: pipe for pipe in result.pipes}
        assert {"write_research_brief", "find_key_findings", "draft_brief"} <= set(pipes_by_code)

        # Level 1: the main pipe reconciled from the root's PipeSignature header to the concrete controller.
        main_pipe = pipes_by_code["write_research_brief"]
        assert not main_pipe.is_signature
        assert isinstance(main_pipe, PipeSequence)

        # Level 2: each sub-pipe reconciled from the controller's forward-declared header to a concrete operator.
        for sub_code in ("find_key_findings", "draft_brief"):
            sub_pipe = pipes_by_code[sub_code]
            assert not sub_pipe.is_signature, f"{sub_code} should be concrete after merge"
            assert isinstance(sub_pipe, PipeLLM)

        # No header left unsatisfied anywhere in the library -> runnable.
        assert result.pending_signatures == []
