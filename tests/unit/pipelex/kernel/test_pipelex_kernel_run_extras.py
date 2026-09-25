"""`PipelexKernel.make` carrying the host's opaque extras.

The kernel tier is the direct programmatic entry point — the one a host embeds
without going through `pipeline_run_setup` — so it needs the same seam the
pipeline entry points have. Without it a kernel-minted run is permanently
unlabelled and its host has no supported way to say otherwise, while
`docs/under-the-hood/pipelex-kernel.md` lists the field among what
`job_metadata.run_metadata` holds.
"""

import pytest

from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.system.pipe_run_mode import PipeRunMode


class TestPipelexKernelRunExtras:
    def test_supplied_extras_land_on_the_runs_metadata(self) -> None:
        kernel = PipelexKernel.make(
            storage_scope="test/scope",
            run_mode=PipeRunMode.DRY,
            user_id="test-user",
            extras={"organization": "org_acme"},
        )

        assert kernel.job_metadata.run_metadata.extras == {"organization": "org_acme"}

    def test_omitting_them_leaves_an_empty_mapping(self) -> None:
        """Every existing caller omits the field; an omission is an empty facet, not an error."""
        kernel = PipelexKernel.make(storage_scope="test/scope", run_mode=PipeRunMode.DRY, user_id="test-user")

        assert kernel.job_metadata.run_metadata.extras == {}

    def test_two_kernels_do_not_share_one_default_mapping(self) -> None:
        """A mutable default shared between runs would leak one host's extras into another's."""
        first = PipelexKernel.make(storage_scope="test/scope", run_mode=PipeRunMode.DRY, user_id="test-user")
        second = PipelexKernel.make(storage_scope="test/scope", run_mode=PipeRunMode.DRY, user_id="test-user")

        first.job_metadata.run_metadata.extras["organization"] = "org_acme"

        assert second.job_metadata.run_metadata.extras == {}

    def test_a_malformed_mapping_is_refused_when_the_kernel_is_minted(self) -> None:
        """The field's validator is what makes this fail here rather than inside a later capture."""
        with pytest.raises(ValueError, match="extras"):
            PipelexKernel.make(
                storage_scope="test/scope",
                run_mode=PipeRunMode.DRY,
                user_id="test-user",
                extras={"Organization": "org_acme"},
            )
