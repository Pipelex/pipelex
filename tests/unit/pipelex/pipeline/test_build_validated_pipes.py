"""Pin the ``build_validated_pipes`` projection contract (the C-8 fix).

``build_validated_pipes`` turns a dry-run result map into the ``validated_pipes`` JSON list that the
agent CLI + builder ops publish. Two guarantees must hold, and a regression in either would silently
corrupt the published contract while the rest of the suite stays green:

1. **Truthful status.** A FAILURE (e.g. an ``allowed_to_fail`` pipe) and a SKIPPED (cross-package)
   must surface as ``"FAILURE"`` / ``"SKIPPED"`` — NOT flattened to ``"SUCCESS"`` (the exact bug the
   C-8 fix removed). The old callers hardcoded an all-``"SUCCESS"`` list.
2. **Namespaced identity.** Each entry's ``pipe_code`` field carries the namespaced ``pipe_ref``
   (``domain.code``), never the bare ``code`` — one unambiguous identity across every validate surface.

Pure unit test (no Pipelex boot, no inference): drives the projection over a hand-built result map.
"""

from pipelex.pipeline.bundle_validator import DryRunOutput, DryRunStatus
from pipelex.pipeline.validate_bundle import build_validated_pipes


class TestBuildValidatedPipes:
    def test_projection_surfaces_real_status_and_namespaced_ref(self) -> None:
        # The map is keyed by namespaced pipe_ref in production; the bare `code` is deliberately
        # different from the `pipe_ref` so a regression to the bare code would be caught.
        dry_run_result: dict[str, DryRunOutput] = {
            "domain_a.impl": DryRunOutput(pipe_code="impl", pipe_ref="domain_a.impl", status=DryRunStatus.SUCCESS),
            "domain_a.flaky": DryRunOutput(
                pipe_code="flaky",
                pipe_ref="domain_a.flaky",
                status=DryRunStatus.FAILURE,
                error_message="allowed to fail",
            ),
            "domain_b.xpkg": DryRunOutput(pipe_code="xpkg", pipe_ref="domain_b.xpkg", status=DryRunStatus.SKIPPED),
        }

        entries = build_validated_pipes(dry_run_result)

        by_ref = {entry["pipe_code"]: entry["status"] for entry in entries}
        # Every entry is keyed by its namespaced pipe_ref, never the bare code.
        assert set(by_ref) == {"domain_a.impl", "domain_a.flaky", "domain_b.xpkg"}
        assert not ({"impl", "flaky", "xpkg"} & set(by_ref))
        # Status is reported truthfully — the FAILURE and SKIPPED are NOT flattened to SUCCESS.
        assert by_ref["domain_a.impl"] == DryRunStatus.SUCCESS
        assert by_ref["domain_a.flaky"] == DryRunStatus.FAILURE
        assert by_ref["domain_b.xpkg"] == DryRunStatus.SKIPPED
