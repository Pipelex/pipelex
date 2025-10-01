domain = "pipe_design"
definition = "Build and process pipes."

[concept]
PipeSignature = "A pipe contract which says what the pipe does, not how it does it: code (the pipe code in snake_case), type, description, inputs, output."
PipeSpec = "A structured spec for a pipe (union)."
# Pipe controllers
PipeBatchSpec = "A structured spec for a pipe batch."
PipeConditionSpec = "A structured spec for a pipe condition."
PipeParallelSpec = "A structured spec for a pipe parallel."
PipeSequenceSpec = "A structured spec for a pipe sequence."
# Pipe operators
PipeFuncSpec = "A structured spec for a pipe func."
PipeImgGenSpec = "A structured spec for a pipe img gen."
# PipeComposeSpec = "A structured spec for a pipe jinja2."
PipeLLMSpec = "A structured spec for a pipe llm."
PipeOcrSpec = "A structured spec for a pipe ocr."
PipeFailure = "Details of a single pipe failure during dry run."

[pipe]

[pipe.detail_pipe_spec]
type = "PipeCondition"
definition = "Route by signature.type to the correct spec emitter."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "ConceptSpec" }
output = "Dynamic"
expression = "pipe_signature.type"
default_pipe_code = "continue"

[pipe.detail_pipe_spec.pipe_map]
PipeSequence  = "detail_pipe_sequence"
PipeParallel  = "detail_pipe_parallel"
PipeCondition = "detail_pipe_condition"
PipeLLM       = "detail_pipe_llm"
PipeOcr       = "detail_pipe_ocr"
PipeImgGen    = "detail_pipe_img_gen"

# ────────────────────────────────────────────────────────────────────────────────
# PIPE CONTROLLERS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_sequence]
type = "PipeLLM"
definition = "Build a PipeSequenceSpec from the signature (children referenced by code)."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeSequenceSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeSequenceSpec to orchestrate a sequence of pipe steps that will run one after the other.

This PipeSequence is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeSequence related to this signature:
@pipe_signature
"""

[pipe.detail_pipe_parallel]
type = "PipeLLM"
definition = "Build a PipeParallelSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeParallelSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeParallelSpec to orchestrate a bunch of pipe steps that will run in parallel.

This PipeParallel is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeParallel related to this signature:
@pipe_signature
"""

[pipe.detail_pipe_condition]
type = "PipeLLM"
definition = "Build a PipeConditionSpec from the signature (provide expression/pipe_map consistent with children)."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeConditionSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeConditionSpec to route to the correct pipe step based on a conditional expression.

This PipeCondition is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeCondition related to this signature:
@pipe_signature
"""

# ────────────────────────────────────────────────────────────────────────────────
# PIPE OPERATORS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_llm]
type = "PipeLLM"
definition = "Build a PipeLLMSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeLLMSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeLLMSpec to use an LLM to generate a text, or a structured object using different kinds of inputs.
Whatever it's really going to do has already been decided, as you can see:

This PipeLLM is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeLLM related to this signature:
@pipe_signature

If it's a structured generation, indicate it in the system_prompt to clarify the task.
If it's to generate free form text, the prompt_template should indicate to be concise.
If it's to generate an image generation, the prompt_template should indicate to be VERY concise and focus and apply the best practice for image generation.
"""

[pipe.detail_pipe_ocr]
type = "PipeLLM"
definition = "Build a PipeOcrSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeOcrSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeOcrSpec to extract text from an image or a pdf.

This PipeOcr is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeOcr related to this signature:
@pipe_signature
"""

[pipe.detail_pipe_img_gen]
type = "PipeLLM"
definition = "Build a PipeImgGenSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeImgGenSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeImgGenSpec to generate an image from a text prompt.

This PipeImgGen is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeImgGen related to this signature:
@pipe_signature

The inputs for the image has to be a single input which must be a Text or another concept which refines Text.
"""

[pipe.detail_pipe_compose]
type = "PipeLLM"
definition = "Build a PipeComposeSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeComposeSpec"
llm = "llm_to_engineer"
prompt_template = """
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
"""
