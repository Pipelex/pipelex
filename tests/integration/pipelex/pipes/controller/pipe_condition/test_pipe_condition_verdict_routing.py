"""A `PipeCondition` branches on a verdict native's members, live and with no inference.

The verdict natives exist to be branched on: a `Choice` routes by its key, a `Rating` by its level,
and a `YesNo` gates on its probability when its producer reported one. Every branch here is a
`PipeCompose`, so the run is live without spending anything, and the outcome proves the expression
read the member it names rather than whatever a dry run would walk.
"""

from typing import Any

import pytest

from pipelex.pipeline.runner import PipelexMTHDSProtocol

_VERDICT_ROUTING_MTHDS = """
domain = "verdict_routing"
description = "Routing on the members of the verdict natives"

[concept]
Team = { description = "The team a ticket is routed to", refines = "Choice" }

[pipe.route_by_team]
type = "PipeCondition"
description = "Routes on the option a choice picked"
inputs = { team = "Team" }
output = "Text"
expression = "team.choice"
default_outcome = "fail"

[pipe.route_by_team.outcomes]
billing = "say_billing"
technical = "say_technical"

[pipe.say_billing]
type = "PipeCompose"
description = "Names the billing desk"
inputs = { team = "Team" }
output = "Text"
template = "billing desk, routed as $team"

[pipe.say_technical]
type = "PipeCompose"
description = "Names the technical desk"
inputs = { team = "Team" }
output = "Text"
template = "technical desk, routed as $team"

[pipe.route_by_grade]
type = "PipeCondition"
description = "Routes on the level a rating selected"
inputs = { grade = "Rating" }
output = "Text"
expression = "'severe' if grade.level >= 2 else 'mild'"
default_outcome = "fail"

[pipe.route_by_grade.outcomes]
severe = "say_severe"
mild = "say_mild"

[pipe.say_severe]
type = "PipeCompose"
description = "Names a severe grade"
inputs = { grade = "Rating" }
output = "Text"
template = "severe at level $grade"

[pipe.say_mild]
type = "PipeCompose"
description = "Names a mild grade"
inputs = { grade = "Rating" }
output = "Text"
template = "mild at level $grade"

[pipe.gate_by_probability]
type = "PipeCondition"
description = "Gates on the probability a yes/no verdict carries, when it carries one"
inputs = { approved = "YesNo" }
output = "Text"
expression = "'confident' if approved.probability is not none and approved.probability >= 0.8 else 'unsure'"
default_outcome = "fail"

[pipe.gate_by_probability.outcomes]
confident = "say_confident"
unsure = "say_unsure"

[pipe.say_confident]
type = "PipeCompose"
description = "Names a confident verdict"
inputs = { approved = "YesNo" }
output = "Text"
template = "confident $approved"

[pipe.say_unsure]
type = "PipeCompose"
description = "Names an unsure verdict"
inputs = { approved = "YesNo" }
output = "Text"
template = "unsure $approved"
"""


async def _run(*, pipe_code: str, inputs: dict[str, Any]) -> str:
    response = await PipelexMTHDSProtocol().execute(pipe_code=pipe_code, mthds_contents=[_VERDICT_ROUTING_MTHDS], inputs=inputs)
    return response.pipe_output.main_stuff.as_text.text


@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionVerdictRouting:
    @pytest.mark.parametrize(
        ("choice", "expected"), [("billing", "billing desk, routed as billing"), ("technical", "technical desk, routed as technical")]
    )
    async def test_a_choice_routes_by_its_key(self, choice: str, expected: str) -> None:
        team = {
            "concept": "verdict_routing.Team",
            "content": {"choice": choice, "confidence": 0.7, "probabilities": {"billing": 0.7, "technical": 0.3}},
        }
        assert await _run(pipe_code="route_by_team", inputs={"team": team}) == expected

    @pytest.mark.parametrize(("level", "expected"), [(2, "severe at level 2"), (0, "mild at level 0")])
    async def test_a_rating_routes_by_its_level(self, level: int, expected: str) -> None:
        grade = {"concept": "native.Rating", "content": {"level": level, "probabilities": {"0": 0.2, "1": 0.3, "2": 0.5}}}
        assert await _run(pipe_code="route_by_grade", inputs={"grade": grade}) == expected

    async def test_a_yes_no_gates_on_a_reported_probability(self) -> None:
        approved = {"concept": "native.YesNo", "content": {"yes_no": True, "probability": 0.93}}
        assert await _run(pipe_code="gate_by_probability", inputs={"approved": approved}) == "confident yes"

    async def test_a_yes_no_without_a_probability_reads_as_absent(self) -> None:
        """A bare boolean builds a `YesNo` with `yes_no` alone, and the guard reads its absent probability as `none`."""
        assert await _run(pipe_code="gate_by_probability", inputs={"approved": True}) == "unsure yes"
