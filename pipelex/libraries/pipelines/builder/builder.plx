domain = "builder"
definition = "Auto-generate a Pipelex bundle (concepts + pipes) from a short user brief."

[concept]
UserBrief = "A short, natural-language description of what the user wants."
PlanDraftText = "Natural-language pipeline plan text describing sequences, inputs, outputs."
PipelexBundleSpec = "A Pipelex bundle spec."
PipeFailure = "Details of a single pipe failure during dry run."
DryRunResult = "A result of a dry run of a pipelex bundle spec."
DomainInformation = "A domain information object."

# ────────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────────
[pipe]
[pipe.pipe_builder]
type = "PipeSequence"
description = "This pipe is going to be the entry point for the builder. It will take a UserBrief and return a PipelexBundleSpec."
inputs = { brief = "UserBrief" }
output = "PipelexBundleSpec"
steps = [
    { pipe = "draft_planning_text", result = "plan_draft" },
    { pipe = "parallel_draft_to_specs" },
    { pipe = "materialize_concept_spec_drafts", result = "concept_spec_drafts" },
    { pipe = "materialize_pipe_signatures", result = "pipe_signatures" },
    { pipe = "pipe_builder_domain_information", result = "domain_information" },
    { pipe = "build_concept_spec", batch_over = "concept_spec_drafts", batch_as = "concept_spec_draft", result = "concept_specs" },
    { pipe = "create_pipes_from_signatures", batch_over = "pipe_signatures", batch_as = "pipe_signature", result = "pipe_specs" },
    { pipe = "compile_in_pipelex_bundle_spec", result = "pipelex_bundle_spec" }
    { pipe = "validate_pipelex_bundle_spec", result = "pipelex_bundle_spec" }
]

[pipe.pipe_builder_domain_information]
type = "PipeLLM"
description = "Turn the brief into a DomainInformation object."
inputs = { brief = "UserBrief" }
output = "DomainInformation"
prompt_template = """
Based on the brief output the "domain" of this pipe, and a definition of what it would represent.

Brief:
@brief

For example, if the pipe is about generating a compliance matrix out of a RFP, the domain would be "rfp_compliance_matrix"...
It should be not more than 4 words, in snake_case.
For the definition, i would like to see a short description of what the bundle would represent.
"""

# ────────────────────────────────────────────────────────────────────────────────
# STAGE 1 — plan (natural language pseudo-code, but explicit about IO + sequencing)
# ────────────────────────────────────────────────────────────────────────────────

[pipe.draft_planning_text]
type = "PipeLLM"
description = "Turn the brief into a pseudo-code plan describing controllers, pipes, their inputs/outputs."
inputs = { brief = "UserBrief" }
output = "PlanDraftText"
llm = "llm_to_engineer"
prompt_template = """
Return a PlanDraftText that narrates the pipeline as pseudo-steps (no code):
- Explicitly describe where a sequence/parallel/condition/batch is used
- For each pipe: state the pipe's description, inputs (by name), and outputs (by name),
- Keep it coherent: children pipes referenced by parent sequences must be named consistently


Here is a description of the pipes:
We have pipe controllers:
- PipeLLM: A pipe that uses an LLM to generate a text, or a structured object. It is a vision LLM that can read images.
  CRITICAL: When extracting MULTIPLE items (articles, employees, products), use multiple_output = true with SINGULAR concepts!
  - Create concept "Article" (not "Articles") with fields "item_name", "quantity" (not "item_names", "quantities")
  - Then set multiple_output = true to get a list of Article objects
- PipeSequence: A pipe that executes a sequence of pipes: It needs to reference the pipes it will execute.
- PipeParallel: A pipe that executes a few pipes in parallel. It needs to reference the pipes it will execute. The results of each pipe will be in the working memory. The output MUST BE "Dynamic".
- PipeCondition: A pipe that based on a specific condition, branches to a specific pipe. You have to explain what the expression of the condition is,
    and what the different pipes are that can be executed based on the condition. It needs to reference the pipes it will execute.
- PipeBatch: A pipe that executes a batch of pipes in parallel. It needs to reference the pipe it will execute.
- PipeImgGen: A pipe that uses an LLM to generate an image. VERY IMPORTANT: IF YOU DECIDE TO CREATE A PIPEIMGEN, YOU ALSO HAVE TO CREATE A PIPELLM THAT WILL WRITE THE PROMPT, AND THAT NEEDS TO PRECEED THE PIPEIMGEN, based on the necessary elements.
That means that in the MAIN pipeline, the prompt should NOT be an input. It should be a step that generates the prompt.
- PipeOcr: A pipe that uses an OCR technology to extract text from an image.
VERY IMPORTANT: THE INPUT OF THE PIPEOCR MUST BE NAMED "ocr_input" and it must be either an image or a pdf or a concept which refines one of them.
Usually there is no need to rename a variable or create a new concept, just call it ocr_input, and we'll use the basic PDF concept.
Thats mean that in the sequence, the input should be ocr_input.
So the input of PipeOcr is {ocr_input: "PDF"} or {ocr_input: "Image"} or a concept which refines one of them.

Be very detailed, process by steps.

Brief:
@brief

LIMIT TO 10 DIFFERENT PIPES FOR NOW
"""

# ────────────────────────────────────────────────────────────────────────────────
# STAGE 2 — textual specs (still TEXT, not structured objects yet)
# ────────────────────────────────────────────────────────────────────────────────
[pipe.parallel_draft_to_specs]
type = "PipeParallel"
description = "Generate ConceptSpecDraftsText and PipeSignaturesText in parallel from plan draft."
inputs = { plan_draft = "PlanDraftText", brief = "UserBrief" }
output = "Dynamic"
parallels = [
    { pipe = "draft_to_conceptspecs_text",   result = "concept_spec_drafts_text" },
    { pipe = "draft_to_pipesignatures_text", result = "pipe_signatures_text" },
]

[pipe.draft_to_conceptspecs_text]
type = "PipeLLM"
description = "From PlanDraftText (+ brief), extract ConceptSpecsText (codes, descriptions, structure hints) in TEXT."
inputs = { plan_draft = "PlanDraftText", brief = "UserBrief" }
output = "Text"
llm = "llm_to_engineer"
prompt_template = """
You will receive a plan for a Pipelex pipeline.
Each pipeline will take inputs and output. Those inputs/output are represented as concepts.

Return ConceptSpecsText capturing all concepts used in the plan:
- Use PascalCase for concept codes
- Provide a short description per concept
- Include structure hints as plain text (fields, types) IF IT IS needed.

CRITICAL RULE: Concepts must represent SINGLE ENTITIES, never collections!
- Create "Article" not "Articles"
- Create "Employee" not "Employees"
- Use SINGULAR field names: "item_name" not "item_names", "quantity" not "quantities"
- If you need multiple items, the PipeLLM will use multiple_output=true to generate a LIST of the concept

If you need structure for your concept, to isolate/extract some precise information, assign a structure:
Here is how the structure as to be described:
A dict with:
- key: the field name in snake_case (ALWAYS SINGULAR)
- value: a dict with:
  - definition: the definition of the field, in natural language
  - type: the type of the field (text, integer, boolean, number)
  - required: whether the field is required
  - default_value: the default value of the field

You can have multiple fields if needed, but each field should represent a single value.

Otherwise, there are native concepts that you can use:
If the concept you want to create is JUST a text, assign "Text" to the 'refines' field, and no structure field.
If the concept you want to create is JUST an image, assign "Image" to the 'refines' field, and no structure field.
If the concept you want to create is JUST a PDF, assign "PDF" to the 'refines' field, and no structure field.
If the concept you want to create is JUST a Number, assign "Number" to the 'refines' field, and no structure field.

DO NOT redefine native concepts:
- Text
- Image
- PDF
- Number
- Page
If you need one of these, you will later on use them, but you should NOT REDEFINE THEM.
Plan:
@plan_draft

Brief:
@brief

Remember: Create concepts for SINGLE entities. Lists are handled by PipeLLM with multiple_output=true.
"""

[pipe.draft_to_pipesignatures_text]
type = "PipeLLM"
description = "From PlanDraftText (+ brief), extract PipeSignaturesText in TEXT."
inputs = { plan_draft = "PlanDraftText", brief = "UserBrief" }
output = "Text"
llm = "llm_to_engineer"
prompt_template = """
Return PipeSignaturesText listing every pipe to build:
- For each pipe: give a unique snake_case pipe_code, type, definition, inputs (by concept code/name), output, and important_features
- Controller pipes must reference children by their codes consistently
- The Pipe Controllers, if they mention pipes, they should always mention existing pipes.
- Add as much details as possible for the description.

Here are the ESSENTIAL features for each pipe type that should be included in important_features (only include these key ones):

**PipeLLM**: A pipe that uses an LLM to generate a text, or a structured object. It is a vision LLM that can read images.
The inputs of the PipeLLM should be:
The variables tagged in the prompt template (with $ or @). If there are no variables, the inputs should be empty.
The ouput should be the concept code of the output
- prompt_template: The prompt template with variable substitution ($ for inline, @ for blocks)
- multiple_output: true if generating multiple number of outputs: That means it will output a LIST of the CONCEPT!

CRITICAL RULE FOR PIPELLM:
- If extracting MULTIPLE items (like multiple articles, employees, products), use multiple_output = true
- The concept should represent ONE SINGLE item (Article, Employee, Product)
- DO NOT create concepts with plural field names like "item_names", "quantities"
- Instead: use multiple_output = true with singular concept fields like "item_name", "quantity"
- Example: To extract multiple articles, create concept "Article" with fields "item_name", "quantity", then use multiple_output = true

**PipeSequence**: A pipe that executes a sequence of pipes: It needs to reference the pipes it will execute.
The inputs of the PipeSequence should be all the necessary inputs in the below steps, and the inputs that are NOT generated by intermediate steps.
The output should be the concept code of the output of the last step.
- steps: List of pipe codes to execute in order, with result names
- Each step format: {"pipe": "pipe_code", "result": "result_name"}
- Can include batch operations: {"pipe": "pipe_code", "batch_over": "list_input", "batch_as": "item_name", "result": "result_name"}

**PipeParallel**: A pipe that executes a few pipes in parallel. It needs to reference the pipes it will execute.
The inputs of the PipeParallel should be all the necessary inputs in the below steps
The output should be the concept code of the output of the last step.
The results of each pipe will be in the working memory.
- parallels: List of pipes to execute in parallel
- Each parallel format: {"pipe": "pipe_code", "result": "result_name"}

**PipeCondition**: A pipe that based on a specific condition, branches to a specific pipe. You have to explain what the expression of the condition is,
    and what the different pipes are that can be executed based on the condition. It needs to reference the pipes it will execute.
The inputs of the PipeCondition should be all the necessary inputs in the below steps
The output should be the concept code of the output of all the steps, except if the outputs are different, then its "Dynamic"
- expression: Direct expression to evaluate (e.g., "task_result.status")
- pipe_map: Dictionary mapping condition results to pipe codes (e.g., {"completed": "success_pipe", "failed": "failure_pipe"})
- default_pipe_code: Fallback pipe when no conditions match

**PipeBatch**: A pipe that executes a batch of pipes in parallel. It needs to reference the pipe it will execute.
- branch_pipe_code: The pipe code to execute for each item
- input_list_name: Name of the list to iterate over
- input_item_name: Name for individual items within each execution

**PipeImgGen**: A pipe that uses an LLM to generate an image.
The inputs of the PipeImgGen should be: {prompt: ImgGenPrompt}
The output should be the concept code that refines Image.
- img_gen_prompt: Static prompt for image generation (if using static prompt)
- nb_output: Number of images to generate (default 1)
VERY IMPORTANT: IF YOU DECIDE TO CREATE A PIPEIMGEN, YOU ALSO HAVE TO CREATE A PIPELLM THAT WILL WRITE THE PROMPT, AND THAT NEEDS TO PRECEED THE PIPEIMGEN, based on the necessary elements.
THERFORE, the OUTPUT OF THIS PIPELLM should be a VARIABLE NAMED "prompt" that will be used as input for the PipeImgGen.
That means that in the MAIN pipeline, the prompt should NOT be an input. It should be a step that generates the prompt.

**PipeOcr**: A pipe that uses an LLM to extract text from an image.
- The INPUTS of this pipe is only "ocr_input" and it must be either an image or a pdf or a concept which refines one of them.
- Usually there is no need to rename a variable or create a new concept, just call it ocr_input, and we'll use the basic PDF concept. Thats mean that in the sequence, the input should be ocr_input.
So the input of PipeOcr is {ocr_input: "PDF"} or {ocr_input: "Image"} or a concept which refines one of them.

**PipeFunc**: A pipe that executes a custom Python function.
- function_name: Name of the Python function to call

**PipeJinja2**: A pipe that uses Jinja2 to render a template.
- jinja2: Raw Jinja2 template string OR
- jinja2_name: Name reference to a template (use one or the other)

Plan:
@plan_draft

Brief:
@brief

No more than 10 PipeSignatures
"""

# ────────────────────────────────────────────────────────────────────────────────
# STAGE 3 — materialize: TEXT → real objects (ConceptSpec[], PipeSignature[])
# ────────────────────────────────────────────────────────────────────────────────

[pipe.materialize_concept_spec_drafts]
type = "PipeLLM"
description = "Turn ConceptSpecsText into ConceptSpec objects."
inputs = { concept_spec_drafts_text = "Text", brief = "UserBrief" }
output = "concept.ConceptSpecDraft"
multiple_output = true
llm = "llm_to_engineer"
prompt_template = """
Materialize ConceptSpec objects from the ConceptSpecsText.
Do not change the information in the input. Just organize the information

ConceptSpecs:
@concept_spec_drafts_text

Brief:
@brief

LIMIT TO A MAXIMUM OF 5 fields for now
"""

[pipe.materialize_pipe_signatures]
type = "PipeLLM"
description = "Turn PipeSignaturesText into PipeSignature objects that reference the ConceptSpec objects."
inputs = { pipe_signatures_text = "Text", concept_spec_drafts = "concept.ConceptSpecDraft", brief = "UserBrief" }
output = "pipe.PipeSignature"
multiple_output = true
llm = "llm_to_engineer"
prompt_template = """
Materialize PipeSignature objects from the PipeSignaturesText.
- pipe_code MUST be snake_case
- inputs must be a Dict[str, ConceptSpecDraft] referencing the provided ConceptSpecDraft objects. If Its the concept itself, use the concept code in PascalCase.
- output must be a ConceptSpec from the provided set. If Its the concept itself, use the concept code in PascalCase.
- important_features must be a Dict containing the pipe-specific features mentioned in the text

VERY IMPORTANT: A pipe has inputs, and an output. The inputs are a dict of keys in snake_case, corresponding to the variables names in the working memory, and the values are the concept codes in PascalCase.
The output is a concept code in PascalCase.
The field "result" is corresponding to the name of the result of the pipe. It will be used in the inputs of the next pipes.
It is important that they link each other in the right way.

The output concept should be a concepts should be in PascalCase

IMPORTANT:
- THE MAIN PIPE SHOULD CONTAIN IN ITS NAME "main_pipeline"
- IF THERE IS A PipeIMG, VERIFIES THAT THE INPUT PROMPT IS ACTUALLY GENERATED BY A PIPELLM BEFORE THE PIPEIMG.
THIS PIPELLM SHOULD NAME THE RESULT OF ITS PIPE "prompt".

PipeSignatures:
@pipe_signatures_text

ConceptSpecDrafts:
@concept_spec_drafts

Brief:
@brief

No more than 10 PipeSignatures
"""

[pipe.compile_in_pipelex_bundle_spec]
type = "PipeFunc"
description = "Compile the pipelex bundle spec."
inputs = { pipe_specs = "PipeSpec", concept_specs = "ConceptSpec" }
output = "PipelexBundleSpec"
function_name = "compile_in_pipelex_bundle_spec"

[pipe.validate_pipelex_bundle_spec]
type = "PipeSequence"
description = "Validate the pipelex bundle spec with iterative fixing."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec" }
output = "PipelexBundleSpec"
steps = [
    { pipe = "validate_dry_run", result = "failed_pipes" },
    { pipe = "check_validation_status", result = "validation_status" },
    { pipe = "handle_validation_result", result = "pipelex_bundle_spec" }
]

[pipe.check_validation_status]
type = "PipeJinja2"
description = "Check if validation failed by examining if failed_pipes list is empty."
inputs = { failed_pipes = "PipeFailure" }
output = "Text"
jinja2 = "{% if failed_pipes.content.items|length > 0 %}FAILURE{% else %}SUCCESS{% endif %}"

[pipe.handle_validation_result]
type = "PipeCondition"
description = "Handle validation result - continue if success or fix failures once."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipes = "PipeFailure", validation_status = "Text" }
output = "PipelexBundleSpec"
expression = "validation_status.text"

[pipe.handle_validation_result.pipe_map]
SUCCESS = "continue"
FAILURE = "fix_failing_pipes_once"

[pipe.fix_failing_pipes_once]
type = "PipeSequence"
description = "Fix failing pipes once and return the result."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipes = "PipeFailure" }
output = "PipelexBundleSpec"
steps = [
    { pipe = "fix_failing_pipe", batch_over = "failed_pipes", batch_as = "failed_pipe", result = "fixed_pipes" },
    { pipe = "reconstruct_bundle_with_all_fixes", result = "pipelex_bundle_spec" },
    { pipe = "validate_pipelex_bundle_spec", result = "pipelex_bundle_spec" }
]

[pipe.validate_dry_run]
type = "PipeFunc"
description = "Validate the pipelex bundle spec and return only failed pipes."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec" }
output = "PipeFailure"
function_name = "validate_dry_run"

[pipe.continue]
type = "PipeJinja2"
description = "Continue with successful validation - return the bundle unchanged."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec" }
output = "PipelexBundleSpec"
jinja2 = "{{ pipelex_bundle_spec }}"

[pipe.reconstruct_bundle_with_all_fixes]
type = "PipeFunc"
description = "Reconstruct the bundle spec with all the fixed pipes."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", fixed_pipes = "Dynamic" }
output = "PipelexBundleSpec"
function_name = "reconstruct_bundle_with_all_fixes"

