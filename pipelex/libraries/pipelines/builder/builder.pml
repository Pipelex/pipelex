domain = "builder"
definition = "Auto-generate a Pipelex bundle (concepts + pipes) from a short user brief."

[concept]
UserBrief = "A short, natural-language description of what the user wants."
PlanDraftText = "Natural-language pipeline plan text describing sequences, inputs, outputs."
PipelexBundleBlueprint = "A Pipelex bundle blueprint."

# ────────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────────

[pipe.build_drafts_from_brief]
type = "PipeSequence"
description = "Brief → PlanDraftText → (ConceptSpecsText, PipeSignaturesText) → PipeSignature[]."
inputs = { brief = "UserBrief" }
output = "Dynamic"
multiple_output = true
steps = [
    { pipe = "draft_planning_text",          result = "plan_draft" },
    { pipe = "draft_to_conceptspecs_text",   result = "concept_specs_text" },
    { pipe = "draft_to_pipesignatures_text", result = "pipe_signatures_text" },
    { pipe = "materialize_concept_specs",    result = "concept_specs" },
    { pipe = "materialize_pipe_signatures",  result = "pipe_signatures" },
    { pipe = "build_concept_blueprint", batch_over = "concept_specs", batch_as = "concept_spec", result = "concept_blueprints" },
    { pipe = "create_pipes_from_signatures", batch_over = "pipe_signatures", batch_as = "pipe_signature", result = "pipe_blueprints" },
    # { pipe = "compile_in_pipelex_bundle_blueprint", result = "pipelex_bundle_blueprint" }
]

# ────────────────────────────────────────────────────────────────────────────────
# STAGE 1 — plan (natural language pseudo-code, but explicit about IO + sequencing)
# ────────────────────────────────────────────────────────────────────────────────

[pipe.draft_planning_text]
type = "PipeLLM"
description = "Turn the brief into a pseudo-code plan describing controllers, pipes, their inputs/outputs."
inputs = { brief = "UserBrief" }
output = "PlanDraftText"
llm = "llm_to_engineer"
structuring_method = "preliminary_text"
prompt_template = """
Return a PlanDraftText that narrates the pipeline as pseudo-steps (no code):
- Explicitly describe where a sequence/parallel/condition/batch is used
- For each pipe: state the pipe's purpose, inputs (by name), and outputs (by name)
- Keep it coherent: children pipes referenced by parent sequences must be named consistently

Here is a description of the pipes:
We have pipe controllers:
- PipeSequence: A pipe that executes a sequence of pipes
- PipeParallel: A pipe that executes a few pipes in parallel
- PipeCondition: A pipe that based on a specific condition, branches to a specific pipe. You have to explain what the expression of the condition is, and what the different pipes are that can be executed based on the condition.
- PipeBatch: A pipe that executes a batch of pipes in parallel
- PipeLLM: A pipe that uses an LLM to generate a text, or a structured object. It can take an image as input.
- PipeImgGen: A pipe that uses an LLM to generate an image.
- PipeOcr: A pipe that uses an LLM to extract text from an image.


Be very detailed, process by steps.

Brief:
@brief
"""

# ────────────────────────────────────────────────────────────────────────────────
# STAGE 2 — textual specs (still TEXT, not structured objects yet)
# ────────────────────────────────────────────────────────────────────────────────

[pipe.draft_to_conceptspecs_text]
type = "PipeLLM"
description = "From PlanDraftText (+ brief), extract ConceptSpecsText (codes, descriptions, structure hints) in TEXT."
inputs = { plan_draft = "PlanDraftText", brief = "UserBrief" }
output = "Text"
llm = "llm_to_engineer"
structuring_method = "preliminary_text"
prompt_template = """
You will receive a plan for a Pipelex pipeline.
Each pipeline will take inputs and output. Those inputs/output are represented as concepts.

Return ConceptSpecsText capturing all concepts used in the plan:
- Use PascalCase for concept codes
- Provide a short description per concept
- Include structure hints as plain text (fields, types) IF IT IS needed.

Here is how the structure as to be described:
A dict with:
- key: the field name in snake_case
- value: a dict with:
  - definition: the definition of the field, in natural language
  - type: the type of the field
  - item_type: the type of the item of the field
  - key_type: the type of the key of the field
  - value_type: the type of the value of the field
  - choices: the choices of the field
  - required: whether the field is required
  - default_value: the default value of the field

You can have multiple fields if needed.

Plan:
@plan_draft

Brief:
@brief
"""

[pipe.draft_to_pipesignatures_text]
type = "PipeLLM"
description = "From PlanDraftText (+ brief), extract PipeSignaturesText in TEXT."
inputs = { plan_draft = "PlanDraftText", brief = "UserBrief" }
output = "Text"
llm = "llm_to_engineer"
structuring_method = "preliminary_text"
prompt_template = """
Return PipeSignaturesText listing every pipe to build:
- For each pipe: give a unique snake_case pipe_code, type, definition, inputs (by concept code/name), and output
- Controller pipes must reference children by their codes consistently

Add as much details as possible for the description.

Plan:
@plan_draft

Brief:
@brief
"""

# ────────────────────────────────────────────────────────────────────────────────
# STAGE 3 — materialize: TEXT → real objects (ConceptSpec[], PipeSignature[])
# ────────────────────────────────────────────────────────────────────────────────

[pipe.materialize_concept_specs]
type = "PipeLLM"
description = "Turn ConceptSpecsText into ConceptSpec objects."
inputs = { concept_specs_text = "Text", brief = "UserBrief" }
output = "concept.ConceptSpec"
multiple_output = true
llm = "llm_to_engineer"
structuring_method = "preliminary_text"
prompt_template = """
Materialize ConceptSpec objects from the ConceptSpecsText.
Do not change the information in the input. Just organize the information

ConceptSpecs:
@concept_specs_text

Brief:
@brief
"""

[pipe.materialize_pipe_signatures]
type = "PipeLLM"
description = "Turn PipeSignaturesText into PipeSignature objects that reference the ConceptSpec objects."
inputs = { pipe_signatures_text = "Text", concept_specs = "concept.ConceptSpec", brief = "UserBrief" }
output = "pipe.PipeSignature"
multiple_output = true
llm = "llm_to_engineer"
structuring_method = "preliminary_text"
prompt_template = """
Materialize PipeSignature objects from the PipeSignaturesText.
- pipe_code MUST be snake_case
- inputs must be a Dict[str, ConceptSpec] referencing the provided ConceptSpec objects
- output must be a ConceptSpec from the provided set

PipeSignatures:
@pipe_signatures_text

ConceptSpecs:
@concept_specs

Brief:
@brief
"""

[pipe.compile_in_pipelex_bundle_blueprint]
type = "PipeLLM"
description = "Compile the pipelex bundle blueprint."
inputs = { pipe_blueprints = "PipeBlueprint", concept_blueprints = "ConceptBlueprint" }
output = "PipelexBundleBlueprint"
llm = "llm_to_engineer"
structuring_method = "preliminary_text"
prompt_template = """
Compile the pipelex bundle blueprint.

PipeBlueprints:
@pipe_blueprints

ConceptBlueprints:
@concept_blueprints
"""

