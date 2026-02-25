import pytest
from pydantic import ValidationError

from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome


class TestPipeConditionBlueprint:
    def test_pipe_dependencies_correct(self):
        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"status": "Text"},
            output="Text",
            expression="status",
            outcomes={"active": "process_active", "inactive": "process_inactive"},
            default_outcome="process_default",
        )
        assert blueprint.pipe_dependencies == {"process_active", "process_inactive", "process_default"}

        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"type": "Text"},
            output="Text",
            expression="type",
            outcomes={"A": "handle_a"},
            default_outcome=SpecialOutcome.FAIL,
        )
        assert blueprint.pipe_dependencies == {"handle_a"}

        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"flag": "Text"},
            output="Text",
            expression="flag",
            outcomes={"yes": "process_yes", "no": "process_no"},
            default_outcome=SpecialOutcome.CONTINUE,
        )
        assert blueprint.pipe_dependencies == {"process_yes", "process_no"}

    def test_validate_outcome_map_correct(self):
        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"value": "Text"},
            output="Text",
            expression="value",
            outcomes={"high": "process_high"},
            default_outcome="process_default",
        )
        assert blueprint.outcomes == {"high": "process_high"}

        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"status": "Text"},
            output="Text",
            expression="status",
            outcomes={"active": "process_active", "inactive": "process_inactive"},
            default_outcome="process_default",
        )
        assert len(blueprint.outcomes) == 2

    def test_validate_outcome_map_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            PipeConditionBlueprint(
                description="lorem ipsum",
                inputs={"value": "Text"},
                output="Text",
                expression="value",
                outcomes={},
                default_outcome="process_default",
            )
        assert "PipeConditionBlueprint must have at least one mapping in outcomes" in str(exc_info.value)
