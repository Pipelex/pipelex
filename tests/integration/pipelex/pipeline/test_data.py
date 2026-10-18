from typing import ClassVar

from mthds.protocol.pipeline_inputs import PipelineInputs


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

    # The literal a lane the condition holds renders to, text of the expression the absence reason must not quote.
    HELD_LANE_LITERAL: ClassVar[str] = "hold_at_the_depot_quietly"
    # A sequence whose condition resolves a held lane to 'continue', and whose next step force-unwraps its absent result.
    CONTINUE_THEN_FORCE_MTHDS: ClassVar[str] = """
domain      = "condition_faults_routing"
description = "Stamp a parcel once it is routed down a lane"
main_pipe   = "route_and_stamp"

[concept]
Parcel = "A parcel waiting at the sorting bench"

[pipe.route_and_stamp]
type        = "PipeSequence"
description = "Route the parcel, then stamp it"
inputs      = { parcel = "Parcel", lane = "Text" }
output      = "Parcel"
steps       = [{ pipe = "route_parcel", result = "routed" }, { pipe = "stamp_parcel", result = "stamped" }]

[pipe.route_parcel]
type                = "PipeCondition"
description         = "Choose the lane a parcel goes down, or hold it"
inputs              = { parcel = "Parcel", lane = "Text" }
output              = "Parcel?"
expression_template = "{% if lane.text == 'hold' %}hold_at_the_depot_quietly{% else %}standard{% endif %}"
outcomes            = { standard = "send_standard" }
default_outcome     = "continue"

[pipe.send_standard]
type        = "PipeCompose"
description = "Note the parcel onto the standard lane"
inputs      = { parcel = "Parcel" }
output      = "Parcel"
template    = "Standard: $parcel"

[pipe.stamp_parcel]
type        = "PipeCompose"
description = "Stamp the routed parcel, which must be present"
inputs      = { routed = "Parcel!" }
output      = "Parcel"
template    = "Stamped: $routed"
"""


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


class ExecuteRequestIdTestData:
    """A bundle that runs without inference, to see which job `execute` hands its `PipeRunProtocol`."""

    REQUEST_ID: ClassVar[str] = "req-execute-7f3a"

    COMPOSE_MTHDS: ClassVar[str] = """
domain = "execute_request_id"
description = "A single compose step, which runs without calling a model"

[pipe.restate]
type = "PipeCompose"
description = "Restate the topic"
inputs = { topic = "Text" }
output = "Text"
template = "About {{ topic }}"
"""


class LogMarkupTestData:
    """A nested method run live, every model call answered by a stand-in worker, to read what its log messages say."""

    MAIN_PIPE: ClassVar[str] = "profile_company"

    INPUTS: ClassVar[PipelineInputs] = {"brief": "Acme builds reusable rockets in Toulouse and sells launches to research labs."}

    MTHDS: ClassVar[str] = """
domain = "log_markup_check"
description = "Describe a company, structure it, summarize it two ways at once, route and compose a report"
main_pipe = "profile_company"

[concept.Company]
description = "A company"

[concept.Company.structure]
name = { type = "text", description = "The company's name" }
sector = { type = "text", description = "The company's sector" }

[concept.ShortSummary]
description = "A one-sentence summary"
refines = "Text"

[concept.DetailedSummary]
description = "A detailed summary"
refines = "Text"

[pipe.profile_company]
type = "PipeSequence"
description = "Describe the company, structure it, summarize it and compose the report"
inputs = { brief = "Text" }
output = "Text"
steps = [
  { pipe = "describe_company", result = "description" },
  { pipe = "structure_company", result = "company" },
  { pipe = "summarize_company", result = "summaries" },
  { pipe = "route_report", result = "report" },
]

[pipe.describe_company]
type = "PipeLLM"
description = "Describe the company the brief is about"
inputs = { brief = "Text" }
output = "Text"
prompt = "Describe the company this brief is about: $brief"

[pipe.structure_company]
type = "PipeLLM"
description = "Structure the description as a company"
inputs = { description = "Text" }
output = "Company"
prompt = "Read the company out of this description: $description"

[pipe.summarize_company]
type = "PipeParallel"
description = "Summarize the description in one sentence and in detail, at once"
inputs = { description = "Text" }
output = "Composite"
add_each_output = true
branches = [
  { pipe = "summarize_short", result = "short_summary" },
  { pipe = "summarize_detailed", result = "detailed_summary" },
]

[pipe.summarize_short]
type = "PipeLLM"
description = "Summarize in one sentence"
inputs = { description = "Text" }
output = "ShortSummary"
prompt = "Summarize in one sentence: $description"

[pipe.summarize_detailed]
type = "PipeLLM"
description = "Summarize in detail"
inputs = { description = "Text" }
output = "DetailedSummary"
prompt = "Summarize in detail: $description"

[pipe.route_report]
type = "PipeCondition"
description = "Pick the report's shape"
inputs = { company = "Company", short_summary = "ShortSummary" }
output = "Text"
expression_template = "{{ 'compact' }}"
default_outcome = "compose_report"

[pipe.route_report.outcomes]
compact = "compose_report"

[pipe.compose_report]
type = "PipeCompose"
description = "Compose the report"
inputs = { company = "Company", short_summary = "ShortSummary" }
output = "Text"
template = "{{ company.name }} works in {{ company.sector }}: {{ short_summary.text }}"
"""


class SummaryEventsTestData:
    """A small method run live on two models, every model call answered by a stand-in worker, to read the events it ends with."""

    MAIN_PIPE: ClassVar[str] = "brief_company"

    INPUTS: ClassVar[PipelineInputs] = {"brief": "Acme builds reusable rockets in Toulouse and sells launches to research labs."}

    MTHDS: ClassVar[str] = """
domain = "summary_events_check"
description = "Describe a company, structure it and pitch it, on two models"
main_pipe = "brief_company"

[concept.Company]
description = "A company"

[concept.Company.structure]
name = { type = "text", description = "The company's name" }
sector = { type = "text", description = "The company's sector" }

[pipe.brief_company]
type = "PipeSequence"
description = "Describe the company, structure it and pitch it"
inputs = { brief = "Text" }
output = "Text"
steps = [
  { pipe = "describe_company", result = "description" },
  { pipe = "structure_company", result = "company" },
  { pipe = "pitch_company", result = "pitch" },
]

[pipe.describe_company]
type = "PipeLLM"
description = "Describe the company the brief is about"
inputs = { brief = "Text" }
output = "Text"
model = "$testing-text"
prompt = "Describe the company this brief is about: $brief"

[pipe.structure_company]
type = "PipeLLM"
description = "Structure the description as a company"
inputs = { description = "Text" }
output = "Company"
model = "$testing-text"
prompt = "Read the company out of this description: $description"

[pipe.pitch_company]
type = "PipeLLM"
description = "Pitch the company in one sentence"
inputs = { description = "Text" }
output = "Text"
model = "$writing-creative"
prompt = "Pitch this company in one sentence: $description"
"""


class RenderTimeTemplateTestData:
    """Bundles whose template names a filter its environment lacks inside a branch, which only rendering that branch finds."""

    UNKNOWN_FILTER: ClassVar[str] = "frob_the_lane"
    # Text of the templates that no refusal may quote.
    TEMPLATE_TEXT: ClassVar[str] = "quietly_routed"

    # A condition whose expression parses and compiles, since its unknown filter sits in a branch, and which a run taking
    # that branch cannot render.
    CONDITION_MTHDS: ClassVar[str] = """
domain      = "render_time_template_condition"
description = "Send a parcel down the lane the request names"
main_pipe   = "route_parcel"

[concept]
Parcel = "A parcel waiting at the sorting bench"

[pipe.route_parcel]
type                = "PipeCondition"
description         = "Choose the lane a parcel goes down"
inputs              = { parcel = "Parcel", lane = "Text" }
output              = "Parcel"
expression_template = "{% if lane.text == 'express' %}{{ lane.text | frob_the_lane }}{% else %}quietly_routed{% endif %}"
outcomes            = { express = "send_express" }
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
"""

    # Replaced by the prompt field each case puts the branch in, `prompt` or `system_prompt`.
    PROMPT_FIELD_SLOT: ClassVar[str] = "<prompt-field>"
    # A step whose prompt is only parsed at load, so its unknown filter in a branch passes the load and fails the render.
    LLM_MTHDS: ClassVar[str] = """
domain      = "render_time_template_llm"
description = "Summarize a topic"
main_pipe   = "summarize"

[pipe.summarize]
type        = "PipeLLM"
description = "Summarize the topic"
inputs      = { topic = "Text" }
output      = "Text"
<prompt-field> = "{% if topic %}Summarize {{ topic.text | frob_the_lane }}{% else %}quietly_routed{% endif %}"
"""
    # The other prompt field, which renders, beside the one naming the unknown filter.
    PLAIN_PROMPT: ClassVar[str] = 'prompt = "Summarize $topic"'

    # A filter the deployment's structure-prompt template names and its environment lacks, which no method wrote.
    UNKNOWN_STRUCTURE_FILTER: ClassVar[str] = "frob_the_structure"
    # The deployment's structure-prompt template, edited to name that filter inside a branch.
    BROKEN_STRUCTURE_PROMPT: ClassVar[str] = "{% if class_structure_str %}{{ class_structure_str | frob_the_structure }}{% endif %}"
    # A step with a structured output, whose prompt renders and whose structure prompt is the deployment's template.
    STRUCTURED_LLM_MTHDS: ClassVar[str] = """
domain      = "render_time_template_structure"
description = "Read a parcel label"
main_pipe   = "read_label"

[concept.ParcelLabel]
description = "The label on a parcel"

[concept.ParcelLabel.structure]
recipient = { type = "text", description = "Who the parcel is for" }

[pipe.read_label]
type        = "PipeLLM"
description = "Read the label off a note"
inputs      = { note = "Text" }
output      = "ParcelLabel"
prompt      = "Read the label from $note"
"""


class SecurityRefusalTestData:
    """Runs a security rule refuses, mid-run, before the run and at a template's render, and what none of their events may quote."""

    READ_SCOPE: ClassVar[str] = "org_abc"
    STORAGE_SCOPE: ClassVar[str] = "org_abc/mt_1/run_1"
    EXTRAS: ClassVar[dict[str, str]] = {"org_id": "org_abc"}

    # Another tenant's storage key, which a construct turns into an image URL the next step shows a model.
    FOREIGN_KEY: ClassVar[str] = "pipelex-storage://org_other/mt_y/run_9/assets/payroll.png"
    FORGED_IMAGE_MTHDS: ClassVar[str] = """
domain = "security_refusal_forged_image"
description = "Forge an image URL from plain text, then show the image to a model"
main_pipe = "describe_forged_photo"

[concept.Photo]
description = "A photo with a caption"

[concept.Photo.structure]
caption = { type = "text", description = "The caption" }
picture = { type = "concept", concept_ref = "native.Image", description = "The picture" }

[pipe.describe_forged_photo]
type = "PipeSequence"
description = "Forge a photo from a text, then describe it"
inputs = { where = "Text" }
output = "Text"
steps = [
  { pipe = "forge_photo", result = "photo" },
  { pipe = "describe_photo", result = "description" },
]

[pipe.forge_photo]
type = "PipeCompose"
description = "Build a photo whose URL is the text it was given"
inputs = { where = "Text" }
output = "Photo"

[pipe.forge_photo.construct]
caption = "forged"

[pipe.forge_photo.construct.picture]
url = { template = "{{ where }}" }

[pipe.describe_photo]
type = "PipeLLM"
description = "Describe the photo"
inputs = { photo = "Photo" }
output = "Text"
prompt = \"\"\"
Describe this image.
$photo.picture
\"\"\"
"""

    # A path on the server's disk passed as an image input, which the input seam refuses before the run exists.
    LOCAL_PATH: ClassVar[str] = "/etc/passwd"
    DESCRIBE_IMAGE_MTHDS: ClassVar[str] = """
domain = "security_refusal_input"
description = "Describe an image input"
main_pipe = "describe_image"

[pipe.describe_image]
type = "PipeLLM"
description = "Describe an image"
inputs = { photo = "Image" }
output = "Text"
prompt = \"\"\"
Describe this image.
$photo
\"\"\"
"""

    # A template reading a private name off a value, which passes the load and which the sandbox refuses at render.
    PRIVATE_READ_TEMPLATE: ClassVar[str] = "Talk about {{ topic['_owner'] }}"
    # A template that fails at render for a reason no security rule has, a method the value lacks.
    MISSING_METHOD_TEMPLATE: ClassVar[str] = "Talk about {{ topic.model_dump_json() }}"
    TOPIC: ClassVar[str] = "the quarterly payroll"
    COMPOSE_MTHDS_SLOT: ClassVar[str] = "TEMPLATE_SLOT"
    COMPOSE_MTHDS: ClassVar[str] = """
domain = "security_refusal_template"
description = "Compose a line about a topic"
main_pipe = "say"

[pipe.say]
type = "PipeCompose"
description = "Say something about the topic"
inputs = { topic = "Text" }
output = "Text"
template = "TEMPLATE_SLOT"
"""


class ResolveBundleTestData:
    """Bundles the host-facing resolve cores are pinned with."""

    MAIN_MTHDS: ClassVar[str] = """\
domain = "pipeline"
description = "Pipeline domain"

[concept.Report]
description = "A report"
structure.score = { description = "the score", type = "concept", concept_ref = "Score" }
structure.label = { description = "a label", type = "concept", concept_ref = "Text" }

[pipe.run_pipeline]
type = "PipeSequence"
description = "Run the pipeline"
inputs = { doc = "Text" }
output = "Score"
steps = [{ pipe = "compute_score", result = "score" }]
"""

    STEPS_MTHDS: ClassVar[str] = """\
domain = "pipeline"

[concept.Score]
description = "A score"
structure = { value = { description = "the value", type = "number" } }

[pipe.compute_score]
type = "PipeLLM"
description = "Compute a score"
inputs = { doc = "Text" }
output = "Score"
model = "$quick-reasoning"
prompt = "Compute a score from $doc"
"""

    # The pipe references a concept that no bundle declares — a load-stage library error, translated
    # by the shared cascade into a ValidateBundleError carrying structured validation errors.
    INVALID_MTHDS: ClassVar[str] = """\
domain = "broken"
description = "Broken domain"

[pipe.bad_pipe]
type = "PipeLLM"
description = "References an undeclared concept"
inputs = { doc = "NoSuchConcept" }
output = "Text"
prompt = "Do something with $doc"
"""

    ADDRESS_DEPENDENCY_MTHDS: ClassVar[str] = """\
domain = "host"

[pipe.run_host]
type = "PipeSequence"
description = "Run an installed dependency"
inputs = { doc = "Text" }
output = "Text"
steps = [{ pipe = "github.com/org/pkg->remote.process", result = "result" }]
"""
