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
