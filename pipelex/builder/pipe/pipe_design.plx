domain = "pipe_design"

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
inputs = { plan_draft = "builder.PlanDraft", pipe_signature = "PipeSignature", concept_specs = "builder.ConceptSpec[]" }
output = "Anything"
expression = "pipe_signature.type"
default_outcome = "fail"

[pipe.detail_pipe_spec.outcomes]
PipeSequence  = "detail_pipe_sequence"
PipeParallel  = "detail_pipe_parallel"
PipeCondition = "detail_pipe_condition"
PipeLLM       = "detail_pipe_llm"
PipeExtract   = "detail_pipe_extract"
PipeImgGen    = "detail_pipe_img_gen"
PipeBatch     = "detail_pipe_batch"
PipeCompose   = "detail_pipe_compose"

# ────────────────────────────────────────────────────────────────────────────────
# PIPE CONTROLLERS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_sequence]
type = "PipeLLM"
description = "Build a PipeSequenceSpec from the signature (children referenced by code)."
inputs = { plan_draft = "builder.PlanDraft", pipe_signature = "PipeSignature", concept_specs = "builder.ConceptSpec[]" }
output = "PipeSequenceSpec"
model = "$engineering-structured"
prompt = """
# Orchestrate a sequence of pipe steps that will run one after the other.

@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Html, Image, Document (and note that PDF is a document), Number, Page

@pipe_signature

Based on the pipe signature, build the PipeSequenceSpec.

Note:
- The output concept of a pipe sequence must always be the same as the output concept of the last pipe in the sequence.
"""

[pipe.detail_pipe_parallel]
type = "PipeLLM"
description = "Build a PipeParallelSpec from the signature."
inputs = { plan_draft = "builder.PlanDraft", pipe_signature = "PipeSignature", concept_specs = "builder.ConceptSpec[]" }
output = "PipeParallelSpec"
model = "$engineering-structured"
prompt = """
Orchestrate a set of independent pipes that will run concurrently.

@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Html, Image, Document (and note that PDF is a document), Number, Page

@pipe_signature

Based on the pipe signature, build the PipeParallelSpec.
"""

[pipe.detail_pipe_condition]
type = "PipeLLM"
description = "Build a PipeConditionSpec from the signature (provide expression/outcome consistent with children)."
inputs = { plan_draft = "builder.PlanDraft", pipe_signature = "PipeSignature", concept_specs = "builder.ConceptSpec[]" }
output = "PipeConditionSpec"
model = "$engineering-structured"
prompt = """
Design a PipeConditionSpec to route to the correct pipe based on a conditional expression.

@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Html, Image, Document (and note that PDF is a document), Number, Page

@pipe_signature

Based on the pipe signature, build the PipeConditionSpec.
"""

[pipe.detail_pipe_batch]
type = "PipeLLM"
description = "Build a PipeBatchSpec from the signature."
inputs = { plan_draft = "builder.PlanDraft", pipe_signature = "PipeSignature", concept_specs = "builder.ConceptSpec[]" }
output = "PipeBatchSpec"
model = "$engineering-structured"
prompt = """
Design a PipeBatchSpec to run a pipe in batch.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Html, Image, Document (and note that PDF is a document), Number, Page

Based on the pipe signature, build the PipeBatchSpec.

@pipe_signature
"""

# ────────────────────────────────────────────────────────────────────────────────
# PIPE OPERATORS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_llm]
type = "PipeLLM"
description = "Build a PipeLLMSpec from the signature."
inputs = { plan_draft = "builder.PlanDraft", pipe_signature = "PipeSignature", concept_specs = "builder.ConceptSpec[]" }
output = "PipeLLMSpec"
model = "$engineering-structured"
prompt = """
Design a PipeLLMSpec to use an LLM to generate a text, or a structured object using different kinds of inputs.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Html, Image, Document (and note that PDF is a document), Number, Page

Based on the pipe signature, build the PipeLLMSpec.

@pipe_signature

Notes: 
- If we are generating a structured concept, indicate it in the system_prompt to clarify the task.
- But DO NOT detail the structure in any of the user/system prompts: we will add the schema later. So, don't write a bullet-list of all the attributes to determine.
- If it's to generate free form text, the prompt should indicate to be concise.
- If it's to generate an image generation prompt, the prompt should indicate to be VERY concise and focus and apply the best practice for image generation.
"""

[pipe.detail_pipe_extract]
type = "PipeLLM"
description = "Build a PipeExtractSpec from the signature."
inputs = { plan_draft = "builder.PlanDraft", pipe_signature = "PipeSignature", concept_specs = "builder.ConceptSpec[]" }
output = "PipeExtractSpec"
model = "$engineering-structured"
prompt = """
Design a PipeExtractSpec to extract text from an image or a pdf.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Html, Image, Document (and note that PDF is a document), Number, Page

Based on the pipe signature, build the PipeExtractSpec.

@pipe_signature
"""

[pipe.detail_pipe_img_gen]
type = "PipeLLM"
description = "Build a PipeImgGenSpec from the signature."
inputs = { plan_draft = "builder.PlanDraft", pipe_signature = "PipeSignature", concept_specs = "builder.ConceptSpec[]" }
output = "PipeImgGenSpec"
model = "$engineering-structured"
prompt = """
Your job is to design a PipeImgGenSpec to generate an image from a text prompt.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Html, Image, Document (and note that PDF is a document), Number, Page

Based on the pipe signature, build the PipeImgGenSpec.

@pipe_signature

Notes:
- The inputs for the image has to be a single input which must be a Text or another concept which refines Text.
"""

[pipe.detail_pipe_compose]
type = "PipeLLM"
description = "Build a PipeComposeSpec from the signature."
inputs = { plan_draft = "builder.PlanDraft", pipe_signature = "PipeSignature", concept_specs = "builder.ConceptSpec[]" }
output = "PipeComposeSpec"
model = "$engineering-structured"
prompt = """
Design a PipeComposeSpec to compose content from working memory variables.
Whatever it's really going to do has already been decided as part of this plan:
@plan_draft

You must pick the relevant concepts for inputs and outputs from the following possibilities:
@concept_specs

+ you can use the native concepts: Text, Html, Image, Document (and note that PDF is a document), Number, Page

Based on the pipe signature, build the PipeComposeSpec.

PipeCompose has two modes - choose the appropriate one based on the pipe's purpose:

**Template mode** (for Text/Html output):
- Use when you need to render a template to produce formatted text
- Requires: template (template string), target_format (plain/markdown/html/json/mermaid)
- Output must be Text (or a concept that refines Text), or Html (or a concept that refines Html) if generating HTML content
- **IMPORTANT - Use Pipelex pre-processor syntax in templates:**
  - Use `@ + variable_name` to render an entire object with all its attributes automatically formatted
  - Use `$ + variable_name.field` for inline field access within text
  - Only use raw Jinja2 double-braces when you need a specific single field in isolation
  - **NEVER manually list all attributes** of an object in a template - use @ syntax instead to render the whole object

**Construct mode** (for StructuredContent output):
- Use when you need to assemble a structured object from working memory variables
- Requires: construct (dict mapping field names to composition specs)
- Each field can use:
  - A fixed value (string, number, boolean, list)
  - `{ from = "the_variable" }` to reference a variable directly from working memory
  - `{ from = "the_variable.path" }` to reference a nested field
  - `{ template = "..." }` ONLY when string interpolation is needed (e.g., combining a prefix with a variable)
- **IMPORTANT - Best practices for construct mode:**
  - **PREFER `{ from = "the_variable" }`** for direct object/value assignment
  - **NEVER use templates to manually list attributes** - if you need the whole object, use `{ from = "the_variable" }`
  - Use `{ template = "..." }` only for string composition like prefixes, formatting, or combining multiple fields into a single string

**Examples of CORRECT vs INCORRECT usage:**

WRONG - manually listing attributes in a template:
  summary = { template = "Skills: (( the_obj.skills ))\nExperience: (( the_obj.experience ))" }
CORRECT - direct reference to get the whole object:
  summary = { from = "the_obj" }

WRONG - template mode manually listing attributes:
  template = "Skills: (( the_data.skills ))\nExperience: (( the_data.experience ))"
CORRECT - use @ + the_data to auto-render the whole object:
  template = "(@ + the_data)"

CORRECT - template for string composition (prefix + field):
  code = { template = "INV-($ + the_order.id)" }

@pipe_signature
"""