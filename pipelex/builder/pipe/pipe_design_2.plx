domain = "pipe_design"
description = "Build and process pipes."

[pipe]

[pipe.detail_pipe_spec_2]
type = "PipeCondition"
description = "Route by signature.type to the correct spec emitter."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "ConceptSpec" }
output = "Anything"
expression = "pipe_signature.type"
default_outcome = "fail"

[pipe.detail_pipe_spec_2.outcomes]
PipeSequence  = "detail_pipe_sequence_2"
PipeParallel  = "detail_pipe_parallel_2"
PipeCondition = "detail_pipe_condition_2"
PipeLLM       = "detail_pipe_llm_2"
PipeExtract   = "detail_pipe_extract_2"
PipeImgGen    = "detail_pipe_img_gen_2"
PipeBatch     = "detail_pipe_batch_2"

# ────────────────────────────────────────────────────────────────────────────────
# PIPE CONTROLLERS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_sequence_2]
type = "PipeLLM"
description = "Build a PipeSequenceSpec from the signature (children referenced by code)."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeSequenceSpec"
model = "llm_to_engineer"
prompt = """
# Orchestrate a sequence of pipe steps that will run one after the other.

@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Image, PDF, Number, Page

@pipe_signature

Based on the pipe signature, build the PipeSequenceSpec.

Note:
- The output concept of a pipe sequence must always be the same as the output concept of the last pipe in the sequence.
"""

[pipe.detail_pipe_parallel_2]
type = "PipeLLM"
description = "Build a PipeParallelSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeParallelSpec"
model = "llm_to_engineer"
prompt = """
Orchestrate a set of independent pipes that will run concurrently.

@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Image, PDF, Number, Page

@pipe_signature

Based on the pipe signature, build the PipeParallelSpec.
"""

[pipe.detail_pipe_condition_2]
type = "PipeLLM"
description = "Build a PipeConditionSpec from the signature (provide expression/outcome consistent with children)."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeConditionSpec"
model = "llm_to_engineer"
prompt = """
Design a PipeConditionSpec to route to the correct pipe based on a conditional expression.

@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Image, PDF, Number, Page

@pipe_signature

Based on the pipe signature, build the PipeConditionSpec.
"""

# ────────────────────────────────────────────────────────────────────────────────
# PIPE OPERATORS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_llm_2]
type = "PipeLLM"
description = "Build a PipeLLMSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeLLMSpec"
model = "llm_to_engineer"
prompt = """
Design a PipeLLMSpec to use an LLM to generate a text, or a structured object using different kinds of inputs.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Image, PDF, Number, Page

Based on the pipe signature, build the PipeLLMSpec.

@pipe_signature

Notes: 
- If we are generating a structured concept, indicate it in the system_prompt to clarify the task.
- But DO NOT detail the structure in any of the user/system prompts: we will add the schema later. So, don't write a bullet-list of all the attributes to determine.
- If it's to generate free form text, the prompt should indicate to be concise.
- If it's to generate an image generation prompt, the prompt should indicate to be VERY concise and focus and apply the best practice for image generation.
"""

[pipe.detail_pipe_extract_2]
type = "PipeLLM"
description = "Build a PipeExtractSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeExtractSpec"
model = "llm_to_engineer"
prompt = """
Design a PipeExtractSpec to extract text from an image or a pdf.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Image, PDF, Number, Page

Based on the pipe signature, build the PipeExtractSpec.

@pipe_signature
"""

[pipe.detail_pipe_img_gen_2]
type = "PipeLLM"
description = "Build a PipeImgGenSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeImgGenSpec"
model = "llm_to_engineer"
prompt = """
Your job is to design a PipeImgGenSpec to generate an image from a text prompt.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Image, PDF, Number, Page

Based on the pipe signature, build the PipeImgGenSpec.

@pipe_signature

Notes:
- The inputs for the image has to be a single input which must be a Text or another concept which refines Text.
"""

[pipe.detail_pipe_compose_2]
type = "PipeLLM"
description = "Build a PipeComposeSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeComposeSpec"
model = "llm_to_engineer"
prompt = """
Design a PipeComposeSpec to render a jinja2 template.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Image, PDF, Number, Page

Based on the pipe signature, build the PipeComposeSpec.

@pipe_signature
"""

[pipe.detail_pipe_batch_2]
type = "PipeLLM"
description = "Build a PipeBatchSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeBatchSpec"
model = "llm_to_engineer"
prompt = """
Design a PipeBatchSpec to run a pipe in batch.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Image, PDF, Number, Page

Based on the pipe signature, build the PipeComposeSpec.

@pipe_signature
"""