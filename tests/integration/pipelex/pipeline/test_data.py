from typing import ClassVar


class LocatedRunFailureTestData:
    """Bundles whose runs fail at a nested pipe, one per way a run failure is located."""

    UNSERVED_MODEL_HANDLE: ClassVar[str] = "located-failure-unserved-model"

    # A sequence whose second step names a model the deck does not serve. The inline setting table
    # passes the static check, so the run fails at the model lookup, before any provider is called.
    MODEL_MTHDS: ClassVar[str] = """
domain = "located_failure_model"
description = "A sequence whose second step names a model the deck does not serve"

[pipe.two_steps]
type = "PipeSequence"
description = "Restate the topic, then summarize it"
inputs = { topic = "Text" }
output = "Text"
steps = [
  { pipe = "restate", result = "restated" },
  { pipe = "summarize", result = "summary" },
]

[pipe.restate]
type = "PipeCompose"
description = "Restate the topic"
inputs = { topic = "Text" }
output = "Text"
template = "About {{ topic }}"

[pipe.summarize]
type = "PipeLLM"
description = "Summarize with a model the deck does not serve"
inputs = { restated = "Text" }
output = "Text"
model = { model = "located-failure-unserved-model", temperature = 0.2 }
prompt = "Summarize $restated"
"""

    # A parallel nested in a sequence, whose plural branch feeds a single field of the combined
    # output: the combine fails, in the live run and in the dry run alike.
    PARALLEL_MTHDS: ClassVar[str] = """
domain = "located_failure_parallel"
description = "A parallel whose plural branch feeds a single field, nested in a sequence"

[concept.Idea]
description = "An idea"

[concept.Idea.structure]
title = { type = "text", description = "The idea's title", required = true }

[concept.Summary]
description = "A summary"

[concept.Summary.structure]
text = { type = "text", description = "The summary", required = true }

[concept.Report]
description = "A report"

[concept.Report.structure]
ideas = { type = "concept", concept_ref = "located_failure_parallel.Idea", description = "The ideas", required = true }
summary = { type = "concept", concept_ref = "located_failure_parallel.Summary", description = "The summary", required = true }

[pipe.flow]
type = "PipeSequence"
description = "Analyze the topic"
inputs = { topic = "Text" }
output = "Report"
steps = [{ pipe = "analyze", result = "report" }]

[pipe.analyze]
type = "PipeParallel"
description = "Generate ideas and a summary, combined into a report"
inputs = { topic = "Text" }
output = "Report"
branches = [
  { pipe = "gen_ideas", result = "ideas" },
  { pipe = "summarize", result = "summary" },
]

[pipe.gen_ideas]
type = "PipeLLM"
description = "Generate ideas"
inputs = { topic = "Text" }
output = "Idea[]"
prompt = "Give ideas about $topic"

[pipe.summarize]
type = "PipeLLM"
description = "Summarize"
inputs = { topic = "Text" }
output = "Summary"
prompt = "Summarize $topic"
"""

    # A step force-unwraps ('!') an optional input the caller left out: a caller-facing failure.
    FORCE_MTHDS: ClassVar[str] = """
domain = "located_failure_force"
description = "A sequence whose step force-unwraps an optional input the caller left out"

[pipe.force_flow]
type = "PipeSequence"
description = "Echo an optional clause, asserted present inside"
inputs = { clause = "Text?" }
output = "Text"
steps = [{ pipe = "force_echo", result = "echoed" }]

[pipe.force_echo]
type = "PipeCompose"
description = "Echo the clause, which must be present"
inputs = { clause = "Text!" }
output = "Text"
template = "Clause: {{ clause }}"
"""


class StrictMethodFaultsTestData:
    """Bundles whose runs fail on a fault in the caller's own method, and on faults that are not the caller's."""

    # A sequence whose first step needs an input the caller may leave out of the request.
    MISSING_INPUT_MTHDS: ClassVar[str] = """
domain = "strict_faults_missing_input"
description = "A sequence that greets a name the caller must provide"

[pipe.greet_flow]
type = "PipeSequence"
description = "Greet the name"
inputs = { name = "Text" }
output = "Text"
steps = [{ pipe = "greet", result = "greeting" }]

[pipe.greet]
type = "PipeCompose"
description = "Greet the name"
inputs = { name = "Text" }
output = "Text"
template = "Hello {{ name }}"
"""

    # A parallel nested in a sequence, whose single `Idea` branch feeds a field holding a list of plain
    # texts: the combine refuses it, and no multiplicity change would make it fit, since the field's
    # items are not concept contents. Every pipe is a PipeCompose or a controller.
    PARALLEL_NO_MULTIPLICITY_MTHDS: ClassVar[str] = """
domain = "strict_faults_parallel"
description = "A parallel whose single branch feeds a list of plain texts, nested in a sequence"

[concept.Idea]
description = "One idea"
refines = "Text"

[concept.Overview]
description = "A one-line overview"
refines = "Text"

[concept.Review]
description = "Ideas and an overview"

[concept.Review.structure]
ideas = { type = "list", item_type = "text", description = "The ideas", required = true }
overview = { type = "concept", concept_ref = "strict_faults_parallel.Overview", description = "The overview", required = true }

[pipe.flow]
type = "PipeSequence"
description = "Review the topic"
inputs = { topic = "Text" }
output = "Review"
steps = [{ pipe = "analyze", result = "review" }]

[pipe.analyze]
type = "PipeParallel"
description = "Draft an idea and an overview at the same time"
inputs = { topic = "Text" }
output = "Review"
branches = [
  { pipe = "draft_idea", result = "ideas" },
  { pipe = "write_overview", result = "overview" },
]

[pipe.draft_idea]
type = "PipeCompose"
description = "Draft one idea about the topic"
inputs = { topic = "Text" }
output = "Idea"
template = "An idea about $topic"

[pipe.write_overview]
type = "PipeCompose"
description = "Write a one-line overview"
output = "Overview"
template = "One idea."
"""

    DECK_PRESET: ClassVar[str] = "strict-faults-deck-preset"
    DECK_ALIAS: ClassVar[str] = "strict-faults-deck-alias"
    # A handle the deck's own preset and alias name, which the test profile does not serve.
    DECK_NAMED_UNSERVED_HANDLE: ClassVar[str] = "strict-faults-deck-named-unserved"

    # Replaced by the model reference a test names the step's model with.
    MODEL_REFERENCE_SLOT: ClassVar[str] = "<model-reference>"

    # A step that names its model through a preset or an alias of the deck: the deck names the model.
    DECK_NAMED_MODEL_MTHDS: ClassVar[str] = """
domain = "strict_faults_deck_model"
description = "A step whose model the deck names but does not serve"

[pipe.summarize_flow]
type = "PipeSequence"
description = "Summarize the topic"
inputs = { topic = "Text" }
output = "Text"
steps = [{ pipe = "summarize", result = "summary" }]

[pipe.summarize]
type = "PipeLLM"
description = "Summarize with a model the deck names but does not serve"
inputs = { topic = "Text" }
output = "Text"
model = "<model-reference>"
prompt = "Summarize $topic"
"""

    # A step with a structured output, whose model output the test makes unfit for its structure.
    STRUCTURED_OUTPUT_MTHDS: ClassVar[str] = """
domain = "strict_faults_structured_output"
description = "A step whose structured output the model could not fit"

[concept.Verdict]
description = "A verdict on a claim"

[concept.Verdict.structure]
label = { type = "text", description = "The verdict's label", required = true }

[pipe.judge_flow]
type = "PipeSequence"
description = "Judge the claim"
inputs = { claim = "Text" }
output = "Verdict"
steps = [{ pipe = "judge", result = "verdict" }]

[pipe.judge]
type = "PipeLLM"
description = "Judge the claim"
inputs = { claim = "Text" }
output = "Verdict"
prompt = "Judge this claim: $claim"
"""


class ConditionMethodFaultsTestData:
    """Bundles whose `PipeCondition` refuses the run on a fault in the caller's own method."""

    # Replaced by the inputs, the expression, the outcomes and the default outcome each case gives the condition.
    INPUTS_SLOT: ClassVar[str] = "<inputs>"
    EXPRESSION_SLOT: ClassVar[str] = "<expression>"
    OUTCOMES_SLOT: ClassVar[str] = "<outcomes>"
    DEFAULT_OUTCOME_SLOT: ClassVar[str] = "<default-outcome>"

    # A condition routing a parcel between two lanes, whose expression each case sets.
    ROUTING_MTHDS: ClassVar[str] = """
domain      = "condition_faults_routing"
description = "Send a parcel down the lane the request names"
main_pipe   = "route_parcel"

[concept]
Parcel = "A parcel waiting at the sorting bench"

[pipe.route_parcel]
type            = "PipeCondition"
description     = "Choose the lane a parcel goes down"
inputs          = <inputs>
output          = "Parcel"
expression      = "<expression>"
outcomes        = <outcomes>
default_outcome = "<default-outcome>"

[pipe.send_express]
type        = "PipeCompose"
description = "Note the parcel onto the express lane"
inputs      = { parcel = "Parcel" }
output      = "Parcel"
template    = "Express: $parcel"

[pipe.send_standard]
type        = "PipeCompose"
description = "Note the parcel onto the standard lane"
inputs      = { parcel = "Parcel" }
output      = "Parcel"
template    = "Standard: $parcel"
"""

    # What the condition reads: the parcel its lanes note, and the lane its expression reads.
    PARCEL_AND_LANE_INPUTS: ClassVar[str] = '{ parcel = "Parcel", lane = "Text" }'
    PARCEL_INPUT: ClassVar[str] = '{ parcel = "Parcel" }'
    LANE_INPUT: ClassVar[str] = '{ lane = "Text" }'

    # Two lanes, and a lane the method refuses on purpose.
    LANE_OUTCOMES: ClassVar[str] = '{ express = "send_express", standard = "send_standard", reject = "fail" }'
    # Every outcome, and the default, refuse the run.
    ALL_FAIL_OUTCOMES: ClassVar[str] = '{ reject = "fail" }'


class ConditionExpressionParseTestData:
    """Bundles whose `PipeCondition` declares an expression that does not parse."""

    # A template whose second line opens a tag Jinja2 does not know.
    UNKNOWN_TAG_TEMPLATE_MTHDS: ClassVar[str] = '''
domain      = "condition_faults_routing"
description = "Send a parcel down the lane the request names"
main_pipe   = "route_parcel"

[concept]
Parcel = "A parcel waiting at the sorting bench"

[pipe.route_parcel]
type                = "PipeCondition"
description         = "Choose the lane a parcel goes down"
inputs              = { parcel = "Parcel", lane = "Text" }
output              = "Parcel"
expression_template = """{% if lane == 'express' %}express{% else %}standard
{% frobnicate_the_parcel %}{% endif %}"""
outcomes            = { express = "send_express", standard = "send_standard" }
default_outcome     = "send_standard"

[pipe.send_express]
type        = "PipeCompose"
description = "Note the parcel onto the express lane"
inputs      = { parcel = "Parcel" }
output      = "Parcel"
template    = "Express: $parcel"

[pipe.send_standard]
type        = "PipeCompose"
description = "Note the parcel onto the standard lane"
inputs      = { parcel = "Parcel" }
output      = "Parcel"
template    = "Standard: $parcel"
'''

    # A caller's bundle that is valid on its own, validated beside a host library holding an unparsable condition.
    VALID_CALLER_MTHDS: ClassVar[str] = """
domain      = "harbour_notices"
description = "Post notices on the harbour board"
main_pipe   = "write_board_notice"

[pipe.write_board_notice]
type        = "PipeLLM"
description = "Write the notice for the harbour board"
inputs      = { tide_times = "Text" }
output      = "Text"
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""
