domain = "pipe_design"
description = "Build and process pipes."

[concept]
PipeSignature = "A pipe contract which says what the pipe does, not how it does it: code (the pipe code in snake_case), type, description, inputs, output."
PipeSpec = "A structured spec for a pipe (union)."
# Pipe controllers
PipeBatchSpec = "A structured spec for a PipeBatch."
PipeConditionSpec = "A structured spec for a PipeCondition."
PipeParallelSpec = "A structured spec for a PipeParallel."
PipeSequenceSpec = "A structured spec for a PipeSequence."
# Pipe operators
PipeFuncSpec = "A structured spec for a PipeFunc."
PipeImgGenSpec = "A structured spec for a PipeImgGen."
PipeComposeSpec = "A structured spec for a pipe jinja2."
PipeLLMSpec = "A structured spec for a PipeLLM."
PipeExtractSpec = "A structured spec for a PipeExtract."
PipeFailure = "Details of a single pipe failure during dry run."

[pipe]

[pipe.detail_pipe_spec]
type = "PipeCondition"
description = "Route by signature.type to the correct spec emitter."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "ConceptSpec" }
output = "Dynamic"
expression = "pipe_signature.type"
default_outcome = "continue"

[pipe.detail_pipe_spec.outcomes]
PipeSequence  = "detail_pipe_sequence"
PipeParallel  = "detail_pipe_parallel"
PipeCondition = "detail_pipe_condition"
PipeLLM       = "detail_pipe_llm"
PipeExtract   = "detail_pipe_extract"
PipeImgGen    = "detail_pipe_img_gen"

# ────────────────────────────────────────────────────────────────────────────────
# PIPE CONTROLLERS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_sequence]
type = "PipeLLM"
description = "Build a PipeSequenceSpec from the signature (children referenced by code)."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeSequenceSpec"
model = "llm_to_engineer"
prompt = """
Your job is to design a PipeSequenceSpec to orchestrate a sequence of pipe steps that will run one after the other.

This PipeSequence is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeSequence related to this signature:
@pipe_signature

Here are the concepts you can use for inputs/outputs:
@concept_specs
"""

[pipe.detail_pipe_parallel]
type = "PipeLLM"
description = "Build a PipeParallelSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeParallelSpec"
model = "llm_to_engineer"
prompt = """
Your job is to design a PipeParallelSpec to orchestrate a bunch of pipe steps that will run in parallel.

This PipeParallel is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeParallel related to this signature:
@pipe_signature

Here are the concepts you can use for inputs/outputs:
@concept_specs
"""

[pipe.detail_pipe_condition]
type = "PipeLLM"
description = "Build a PipeConditionSpec from the signature (provide expression/outcome consistent with children)."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeConditionSpec"
model = "llm_to_engineer"
prompt = """
Your job is to design a PipeConditionSpec to route to the correct pipe step based on a conditional expression.

This PipeCondition is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeCondition related to this signature:
@pipe_signature

Here are the concepts you can use for inputs/outputs:
@concept_specs
"""

# ────────────────────────────────────────────────────────────────────────────────
# PIPE OPERATORS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_llm]
type = "PipeLLM"
description = "Build a PipeLLMSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeLLMSpec"
model = "llm_to_engineer"
prompt = """
Your job is to design a PipeLLMSpec to use an LLM to generate a text, or a structured object using different kinds of inputs.
Whatever it's really going to do has already been decided, as you can see:

This PipeLLM is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeLLM related to this signature:
@pipe_signature

If it's a structured generation, indicate it in the system_prompt to clarify the task.
If it's to generate free form text, the prompt should indicate to be concise.
If it's to generate an image generation prompt, the prompt should indicate to be VERY concise and focus and apply the best practice for image generation.

Here are the concepts you can use for inputs/outputs:
@concept_specs
"""

[pipe.detail_pipe_extract]
type = "PipeLLM"
description = "Build a PipeExtractSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeExtractSpec"
model = "llm_to_engineer"
prompt = """
Your job is to design a PipeExtractSpec to extract text from an image or a pdf.

This PipeExtract is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeExtract related to this signature:
@pipe_signature

Here are the concepts you can use for inputs/outputs:
@concept_specs
"""

[pipe.detail_pipe_img_gen]
type = "PipeLLM"
description = "Build a PipeImgGenSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeImgGenSpec"
model = "llm_to_engineer"
prompt = """
Your job is to design a PipeImgGenSpec to generate an image from a text prompt.

This PipeImgGen is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeImgGen related to this signature:
@pipe_signature

The inputs for the image has to be a single input which must be a Text or another concept which refines Text.

Here are the concepts you can use for inputs/outputs:
@concept_specs
"""

[pipe.detail_pipe_compose]
type = "PipeLLM"
description = "Build a PipeComposeSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeComposeSpec"
model = "llm_to_engineer"
prompt = """
Your job is to design a PipeComposeSpec to render a jinja2 template.

This PipeCompose is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeCompose related to this signature:
@pipe_signature

You can ONLY USE THE INPUTS IN THIS PIPE SIGNATURE.

Here are the Jinja2 filters that are supported:
default — Returns a fallback value if the input is undefined (or falsey if enabled).
tag - Returns by tagging it with a title.
format - Apply the given values to a printf-style format string, like string % values.
length — Returns the number of items (alias: count).
upper — Converts a string to uppercase.
lower — Converts a string to lowercase.

Here are the concepts you can use for inputs/outputs:
@concept_specs
"""
