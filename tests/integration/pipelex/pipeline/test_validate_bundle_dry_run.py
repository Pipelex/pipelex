"""Regression tests for the dry-on-load behavior of validate_bundle.

Asserts the dry-run validation surfaced by a broken sub-pipe is propagated
with usable context through ValidateBundleError when validating a bundle.
"""

import tempfile
from pathlib import Path
from typing import ClassVar

import pytest

from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle


class TestData:
    # The top-level PipeSequence recursively calls a sub-pipe that calls back into
    # the controller, blowing the pipe_stack limit. This kind of structural defect
    # passes static validation and only surfaces during dry-run execution — exactly
    # the regression we want validate_bundle's dry-on-load to surface.
    BROKEN_SUB_PIPE_BUNDLE: ClassVar[str] = """
domain = "test_dry_validate"
description = "Top-level controller pipe recursively calls a broken sub-pipe"

[pipe.main_sequence]
type = "PipeSequence"
description = "Main sequence pulling in a broken sub-pipe"
output = "Text"
steps = [
    { pipe = "broken_sub_pipe", result = "next_step" },
]

# Sub-pipe deliberately broken: calls back into the parent controller, creating
# an infinite recursion that only manifests during dry-run pipe execution.
[pipe.broken_sub_pipe]
type = "PipeSequence"
description = "Broken sub-pipe that recurses through main_sequence"
output = "Text"
steps = [
    { pipe = "main_sequence", result = "recursed_step" },
]
"""


class TestValidateBundleDryRunRegression:
    @pytest.mark.asyncio
    async def test_validate_bundle_surfaces_broken_sub_pipe_failure(self):
        """Dry-on-load must fail and the error must mention the broken sub-pipe."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            mthds_file = temp_path / "broken_bundle.mthds"
            mthds_file.write_text(TestData.BROKEN_SUB_PIPE_BUNDLE)

            with pytest.raises(ValidateBundleError) as excinfo:
                await validate_bundle(mthds_file_path=mthds_file, library_dirs=[temp_path])

            error = excinfo.value
            assert error.dry_run_error_message, "Expected ValidateBundleError to carry a dry_run_error_message"
            assert "broken_sub_pipe" in error.message or "missing_input" in error.message, (
                f"Expected the dry-run failure to mention the broken sub-pipe or its missing input; got: {error.message}"
            )
