import pytest

from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_machinery.pipe_blueprint import InputSlotBlueprint

_HEADER = 'domain = "presentation_keys"\ndescription = "Presentation keys"\n'

_COMPOSE = """
[pipe.assemble]
type = "PipeCompose"
description = "Assemble the notice"
inputs = {{ street = "Text" }}
output = "Text"
template = "Works on $street."
{line}
"""

_IMG_GEN = """
[pipe.draw]
type = "PipeImgGen"
description = "Draw the cover"
inputs = {{ topic = "Text" }}
output = "Image"
prompt = "A cover about $topic"
output_filename = "{filename}"
"""

_CONDITION = """
[concept.Claim]
description = "A claim"

[concept.Claim.structure]
severity = {{ description = "Severity", choices = ["high", "low"], required = true }}

[pipe.route]
type = "PipeCondition"
description = "Route the claim"
inputs = {{ claim = "Claim" }}
output = "Text"
expression = "claim.severity"
{outcomes}

[pipe.check]
type = "PipeLLM"
description = "Check"
inputs = {{ claim = "Claim" }}
output = "Text"
prompt = "Check $claim"

[pipe.note]
type = "PipeLLM"
description = "Note"
inputs = {{ claim = "Claim" }}
output = "Text"
prompt = "Note $claim"
"""


def _parse(body: str):
    return MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_HEADER + body)


class TestParserPresentationKeys:
    @pytest.mark.parametrize(
        ("body", "refusal"),
        [
            (_COMPOSE.format(line='activity = ""'), "activity must not be empty"),
            (_COMPOSE.format(line='activity = "Assembling\\nthe notice"'), "no line break"),
            (_COMPOSE.format(line="activity = 3"), "valid string"),
            (_IMG_GEN.format(filename="{{ topic"), "Could not parse the output_filename template"),
            (
                _COMPOSE.format(line='output_filename = "notice"'),
                "allowed only on an operator whose output is file-valued",
            ),
            (
                _CONDITION.format(outcomes='outcomes = { high = { label = "Detailed" }, low = "note" }\ndefault_outcome = "fail"'),
                "must carry its 'pipe'",
            ),
            (
                _CONDITION.format(outcomes='outcomes = { high = { pipe = "check", tone = "red" }, low = "note" }\ndefault_outcome = "fail"'),
                "must be one of positive, caution, negative, neutral",
            ),
            (
                _CONDITION.format(outcomes='outcomes = { high = { pipe = "check", icon = "warning" }, low = "note" }\ndefault_outcome = "fail"'),
                "'icon' is not a key of an outcome table",
            ),
            (
                _CONDITION.format(
                    outcomes=(
                        'outcomes = { high = { pipe = "check", label = "Check" }, low = { pipe = "note", label = "Check" } }\n'
                        'default_outcome = "fail"'
                    )
                ),
                "share the label 'Check'",
            ),
            (
                """
[pipe.write]
type = "PipeLLM"
description = "Write"
inputs = { notes = { concept = "Text", description = "" } }
output = "Text"
prompt = "Write from $notes"
""",
                "description must not be empty",
            ),
        ],
    )
    def test_refused_presentation_keys(self, body: str, refusal: str) -> None:
        """The refusals no `error_type` names, which the corpus cannot carry as entries."""
        with pytest.raises(MthdsParserError, match=refusal):
            _parse(body)

    def test_accepted_presentation_keys_keep_their_words(self) -> None:
        """An activity, an output filename, an outcome table and a described slot survive the parse as authored."""
        blueprint = _parse(
            _COMPOSE.format(line='activity = "Assembling the notice"')
            + _IMG_GEN.format(filename="cover-{{ topic }}")
            + _CONDITION.format(
                outcomes='outcomes = { high = { pipe = "check", label = "Detailed check", tone = "caution" } }\n'
                'default_outcome = { pipe = "note", label = "No check needed" }'
            )
            + """
[pipe.write]
type = "PipeLLM"
description = "Write"
inputs = { notes = { concept = "Text", description = "The host's notes" } }
output = "Text"
prompt = "Write from $notes"
"""
        )
        pipes = blueprint.pipe or {}
        assert pipes["assemble"].activity == "Assembling the notice"
        assert pipes["draw"].output_filename == "cover-{{ topic }}"
        route = pipes["route"]
        assert isinstance(route, PipeConditionBlueprint)
        assert route.outcome_pipes == {"high": "check"}
        assert route.default_outcome_pipe == "note"
        assert route.model_dump(mode="json")["outcomes"] == {"high": {"pipe": "check", "label": "Detailed check", "tone": "caution"}}
        slot = (pipes["write"].inputs or {})["notes"]
        assert isinstance(slot, InputSlotBlueprint)
        assert slot.description == "The host's notes"
