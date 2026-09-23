"""`PipelexKernel.make` carrying the host's opaque analytics groups.

The kernel tier is the direct programmatic entry point — the one a host embeds
without going through `pipeline_run_setup` — so it needs the same seam the
pipeline entry points have. Without it a kernel-minted run is permanently
group-less and its host has no supported way to say otherwise, while
`docs/under-the-hood/pipelex-kernel.md` lists the field among what
`job_metadata.run_metadata` holds.
"""

import pytest

from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.system.pipe_run_mode import PipeRunMode


class TestPipelexKernelAnalyticsGroups:
    def test_supplied_groups_land_on_the_runs_metadata(self) -> None:
        kernel = PipelexKernel.make(
            storage_scope="test/scope",
            run_mode=PipeRunMode.DRY,
            user_id="test-user",
            analytics_groups={"organization": "org_acme"},
        )

        assert kernel.job_metadata.run_metadata.analytics_groups == {"organization": "org_acme"}

    def test_omitting_them_leaves_an_empty_mapping(self) -> None:
        """Every existing caller omits the field; an omission is an empty facet, not an error."""
        kernel = PipelexKernel.make(storage_scope="test/scope", run_mode=PipeRunMode.DRY, user_id="test-user")

        assert kernel.job_metadata.run_metadata.analytics_groups == {}

    def test_two_kernels_do_not_share_one_default_mapping(self) -> None:
        """A mutable default shared between runs would leak one host's groups into another's."""
        first = PipelexKernel.make(storage_scope="test/scope", run_mode=PipeRunMode.DRY, user_id="test-user")
        second = PipelexKernel.make(storage_scope="test/scope", run_mode=PipeRunMode.DRY, user_id="test-user")

        first.job_metadata.run_metadata.analytics_groups["organization"] = "org_acme"

        assert second.job_metadata.run_metadata.analytics_groups == {}

    def test_a_malformed_mapping_is_refused_when_the_kernel_is_minted(self) -> None:
        """The field's validator is what makes this fail here rather than inside a later capture."""
        with pytest.raises(ValueError, match="analytics_groups"):
            PipelexKernel.make(
                storage_scope="test/scope",
                run_mode=PipeRunMode.DRY,
                user_id="test-user",
                analytics_groups={"Organization": "org_acme"},
            )
