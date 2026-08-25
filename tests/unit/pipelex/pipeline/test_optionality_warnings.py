"""The useless-`!` lint's item shape, over hand-built taint analyses.

`build_optionality_warnings` is pure over the controllers' analyses, so the projection it performs —
aggregating observations per (pipe, variable) and stamping a locator on each item — needs no library
window. The cross-flow aggregation itself is pinned over real flows in
`tests/integration/pipelex/pipes/optionals/test_redundant_force_warning.py`; what is pinned here is
the half that walk cannot vary cheaply: how a qualified pipe ref becomes `domain_code` + `pipe_code`.
"""

from pipelex.pipe_controllers.absence_taint import ForceConsumptionInfo, SequenceTaintAnalysis
from pipelex.pipeline.optionality_warnings import build_optionality_warnings
from pipelex.validation_error_types import PipeValidationErrorType


def _redundant_analysis(*, pipe_ref: str) -> SequenceTaintAnalysis:
    """One observation of a `!` on a guaranteed slot — the shape the lint warns about."""
    return SequenceTaintAnalysis(
        liftable_steps=(),
        output_taint=None,
        force_consumptions=(ForceConsumptionInfo(within_pipe_ref=f"{pipe_ref}_flow", pipe_ref=pipe_ref, variable_name="a_out", is_asserting=False),),
    )


class TestOptionalityWarningLocator:
    def test_a_single_segment_domain_splits_at_its_only_dot(self):
        warnings = build_optionality_warnings([_redundant_analysis(pipe_ref="scoring.compute")])

        assert len(warnings) == 1
        assert warnings[0].error_type == PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT
        assert warnings[0].domain_code == "scoring"
        assert warnings[0].pipe_code == "compute"

    def test_a_hierarchical_domain_keeps_its_full_path_in_the_locator(self):
        """A domain is a dotted path, so the ref splits at its LAST dot, not its first."""
        warnings = build_optionality_warnings([_redundant_analysis(pipe_ref="legal.contracts.compute")])

        assert len(warnings) == 1
        assert warnings[0].domain_code == "legal.contracts"
        assert warnings[0].pipe_code == "compute"
