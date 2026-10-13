from collections.abc import Callable

import pytest

from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_machinery.pipe_factory import PipeFactory


def _make_condition(*, default_outcome: str | SpecialOutcome) -> PipeCondition:
    return PipeFactory[PipeCondition].make_from_blueprint(
        domain_code="filings",
        pipe_code="choose_depth",
        blueprint=PipeConditionBlueprint(
            description="Check the filings in depth, quickly, or not at all",
            inputs={"depth": "native.Text"},
            output="native.Text?",
            expression="depth",
            outcomes={
                "detailed": "deep_checks",
                "quick": "quick_check",
                "high risk": "deep_checks",
                "legal/tax review": "legal_check",
                "skip": SpecialOutcome.CONTINUE,
            },
            default_outcome=default_outcome,
        ),
    )


class TestPipeConditionOutcomeGroups:
    @pytest.mark.parametrize(
        ("default_outcome", "pipe_code", "expected_segment"),
        [
            ("file_away", "deep_checks", "outcome_detailed"),
            ("file_away", "quick_check", "outcome_quick"),
            ("file_away", "legal_check", "outcome_legal%2Ftax%20review"),
            ("file_away", "file_away", "default"),
            ("quick_check", "quick_check", "outcome_quick"),
        ],
        ids=["group_of_two_keys", "group_of_one_key", "encoded_key", "group_only_the_default_runs", "default_joins_a_key_group"],
    )
    def test_each_pipe_runs_at_the_segment_of_its_outcome_group(
        self, load_empty_library: Callable[[], str], default_outcome: str, pipe_code: str, expected_segment: str
    ) -> None:
        load_empty_library()
        condition = _make_condition(default_outcome=default_outcome)

        assert condition.outcome_group_segment(pipe_code=pipe_code) == expected_segment
