domain = "pipe"
definition = "Build and process pipes."

[concept]
PipeSignature = "Pseudo-Pipelex step: code, type, description, inputs, output, optional children refs."
PipeBlueprint = "A structured blueprint for a pipe (union)."
# Pipe controllers
PipeBatchSpecBlueprint = "A structured blueprint for a pipe batch."
PipeConditionSpecBlueprint = "A structured blueprint for a pipe condition."
PipeParallelSpecBlueprint = "A structured blueprint for a pipe parallel."
PipeSequenceSpecBlueprint = "A structured blueprint for a pipe sequence."
# Pipe operators
PipeFuncSpecBlueprint = "A structured blueprint for a pipe func."
PipeImgGenSpecBlueprint = "A structured blueprint for a pipe img gen."
PipeJinja2SpecBlueprint = "A structured blueprint for a pipe jinja2."
PipeLLMSpecBlueprint = "A structured blueprint for a pipe llm."
PipeOcrSpecBlueprint = "A structured blueprint for a pipe ocr."
PipeFailure = "Details of a single pipe failure during dry run."

[pipe]
# ────────────────────────────────────────────────────────────────────────────────
# NEW ENTRY POINT — takes PipeSignature[] + ConceptSpecBlueprints → PipeBlueprint[]
# ────────────────────────────────────────────────────────────────────────────────
[pipe.create_pipes_from_signatures]
type = "PipeSequence"
description = "PipeSignature[] + ConceptSpecBlueprints → PipeBlueprint[] (linked & ready)."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint" }
output = "Dynamic"
steps = [
    { pipe = "generate_pipe_blueprint", result = "pipe_blueprint" },
    { pipe = "compile_one_signature_blueprint", result = "compiled_blueprints" },
]

[pipe.generate_pipe_blueprint]
type = "PipeLLM"
description = "Generate a PipeBlueprint from a PipeSignature."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint" }
output = "PipeBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeBlueprint for this signature.

Signature:
@pipe_signature

and here are the existing concepts:
@concept_spec_blueprints

The inputs keys should be snake_case.
The values should be a concept code in PascalCase.
"""

# ────────────────────────────────────────────────────────────────────────────────
# CORE: signature → route to blueprint emitter (unchanged)
# ────────────────────────────────────────────────────────────────────────────────
[pipe.compile_one_signature_blueprint]
type = "PipeCondition"
description = "Route by signature.type to the correct blueprint emitter."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "Dynamic"
expression = "pipe_signature.type"

[pipe.compile_one_signature_blueprint.pipe_map]
PipeSequence  = "emit_sequence_from_signature"
PipeParallel  = "emit_parallel_from_signature"
PipeCondition = "emit_condition_from_signature"
PipeBatch     = "emit_batch_from_signature"
PipeLLM       = "emit_llm_from_signature"
PipeOcr       = "emit_ocr_from_signature"
PipeImgGen    = "emit_imggen_from_signature"
PipeJinja2    = "emit_jinja_from_signature"
PipeFunc      = "emit_func_from_signature"

# ────────────────────────────────────────────────────────────────────────────────
# EMITTERS — one per pipe type, all using the same minimal contract
# (Optionally, emitters could be extended later to read from concept_index.)
# ────────────────────────────────────────────────────────────────────────────────

[pipe.emit_sequence_from_signature]
type = "PipeLLM"
description = "Build a PipeSequenceSpecBlueprint from the signature (children referenced by code)."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeSequenceSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeSequenceSpecBlueprint for this signature.
The Pipe sequence NEEDS to have at least one step.
Orchestrate all the necessary steps to achieve the goal of the pipe.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_spec_blueprints
"""

[pipe.emit_parallel_from_signature]
type = "PipeLLM"
description = "Build a PipeParallelSpecBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeParallelSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeParallelSpecBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_spec_blueprints
"""

[pipe.emit_condition_from_signature]
type = "PipeLLM"
description = "Build a PipeConditionBlueprint from the signature (provide expression/pipe_map consistent with children)."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeConditionSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeConditionSpecBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_spec_blueprints
"""

[pipe.emit_batch_from_signature]
type = "PipeLLM"
description = "Build a PipeBatchSpecBlueprint from the signature (choose branch_pipe_code/params)."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeBatchSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeBatchSpecBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_spec_blueprints
"""

[pipe.emit_llm_from_signature]
type = "PipeLLM"
description = "Build a PipeLLMSpecBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeLLMSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeLLMSpecBlueprint for this signature.

THe prompt is the field "prompt_template" in the PipeLLMSpecBlueprint.
Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_spec_blueprints
"""

[pipe.emit_ocr_from_signature]
type = "PipeLLM"
description = "Build a PipeOcrSpecBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeOcrSpecBlueprint"
prompt_template = """
Return a PipeOcrSpecBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_spec_blueprints
"""

[pipe.emit_imggen_from_signature]
type = "PipeLLM"
description = "Build a PipeImgGenSpecBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeImgGenSpecBlueprint"
prompt_template = """
Return a PipeImgGenSpecBlueprint for this signature.
The inputs for the image has to be only:
input_name : prompt
concept : A concept that refines Text. It should be text
For example:
```
inputs = { prompt: ImgGenPrompt }
```
if ImgGenPrompt is a text concept.

IMPORTANT: imgg_prompt SHOULD BE NONE
IMPORTANT: img_gen_prompt_var_name SHOULD BE NONE
The prompt will need to be be generated by a pipe with the necessary elements.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_spec_blueprints
"""

[pipe.emit_jinja_from_signature]
type = "PipeLLM"
description = "Build a PipeJinja2SpecBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeJinja2SpecBlueprint"
prompt_template = """
Return a PipeJinja2SpecBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_spec_blueprints
"""

[pipe.emit_func_from_signature]
type = "PipeLLM"
description = "Build a PipeFuncSpecBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_spec_blueprints = "concept.ConceptSpecBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeFuncSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeFuncSpecBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_spec_blueprints
"""

# ────────────────────────────────────────────────────────────────────────────────
# PIPE FIXERS — one per pipe type, all fixing specific pipe type issues
# ────────────────────────────────────────────────────────────────────────────────

[pipe.fix_failing_pipe]
type = "PipeCondition"
description = "Route to specific pipe fixer based on the failing pipe type."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "Dynamic"
expression = "failed_pipe.pipe.type"

[pipe.fix_failing_pipe.pipe_map]
PipeLLM = "fix_failing_llm_pipe"
PipeImgGen = "fix_failing_imggen_pipe"
PipeOcr = "fix_failing_ocr_pipe"
PipeFunc = "fix_failing_func_pipe"
PipeJinja2 = "fix_failing_jinja2_pipe"
PipeSequence = "fix_failing_sequence_pipe"
PipeParallel = "fix_failing_parallel_pipe"
PipeCondition = "fix_failing_condition_pipe"
PipeBatch = "fix_failing_batch_pipe"

[pipe.fix_failing_llm_pipe]
type = "PipeLLM"
description = "Fix a failing PipeLLM blueprint based on its specific error."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "PipeLLMSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeLLM blueprint.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeLLMSpecBlueprint. Common LLM pipe issues to fix:
- Missing input variables in the pipe inputs that are referenced in prompt_template
- Incorrect variable names in prompt templates (use $ for inline, @ for blocks)
- Wrong concept types for inputs/outputs
- Missing llm configuration
- Invalid prompt template syntax
"""

[pipe.fix_failing_imggen_pipe]
type = "PipeLLM"
description = "Fix a failing PipeImgGen blueprint based on its specific error."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "PipeImgGenSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeImgGen blueprint.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeImgGenSpecBlueprint. Common ImgGen pipe issues to fix:
- Missing or incorrect prompt input (should be text concept)
- Wrong img_gen_prompt_var_name (should be None or "prompt")
- Invalid imgg_handle configuration
- Missing required inputs for dynamic prompt generation
"""

[pipe.fix_failing_ocr_pipe]
type = "PipeLLM"
description = "Fix a failing PipeOcr blueprint based on its specific error."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "PipeOcrSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeOcr blueprint.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeOcrSpecBlueprint. Common OCR pipe issues to fix:
- Input must be named 'ocr_input' and be of type Image or PDF
- Output should typically be Page (native concept)
- Missing or incorrect input concept types
"""

[pipe.fix_failing_func_pipe]
type = "PipeLLM"
description = "Fix a failing PipeFunc blueprint based on its specific error."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "PipeFuncSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeFunc blueprint.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeFuncSpecBlueprint. Common Func pipe issues to fix:
- Missing or incorrect function_name
- Wrong input/output concept types for the function
- Function not available in registry
"""

[pipe.fix_failing_jinja2_pipe]
type = "PipeLLM"
description = "Fix a failing PipeJinja2 blueprint based on its specific error."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "PipeJinja2SpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeJinja2 blueprint.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeJinja2SpecBlueprint. Common Jinja2 pipe issues to fix:
- Invalid Jinja2 template syntax
- Missing input variables referenced in template
- Wrong concept types for inputs/outputs
"""

[pipe.fix_failing_sequence_pipe]
type = "PipeLLM"
description = "Fix a failing PipeSequence blueprint based on its specific error."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "PipeSequenceSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeSequence blueprint.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeSequenceSpecBlueprint. Common Sequence pipe issues to fix:
- Missing input variables needed by sub-pipes in steps
- Referenced pipe codes in steps that don't exist
- Circular dependencies in step order
- Wrong result names in steps
"""

[pipe.fix_failing_parallel_pipe]
type = "PipeLLM"
description = "Fix a failing PipeParallel blueprint based on its specific error."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "PipeParallelSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeParallel blueprint.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeParallelSpecBlueprint. Common Parallel pipe issues to fix:
- Missing input variables needed by parallel sub-pipes
- Referenced pipe codes that don't exist
- Incompatible output types from parallel branches
"""

[pipe.fix_failing_condition_pipe]
type = "PipeLLM"
description = "Fix a failing PipeCondition blueprint based on its specific error."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "PipeConditionSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeCondition blueprint.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeConditionSpecBlueprint. Common Condition pipe issues to fix:
- Invalid expression or expression_template syntax
- Referenced pipe codes in pipe_map that don't exist
- Missing input variables referenced in expression
- Incompatible output types from different condition branches
"""

[pipe.fix_failing_batch_pipe]
type = "PipeLLM"
description = "Fix a failing PipeBatch blueprint based on its specific error."
inputs = { pipelex_bundle_blueprint = "PipelexBundleBlueprint", failed_pipe = "PipeFailure" }
output = "PipeBatchSpecBlueprint"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeBatch blueprint.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeBatchSpecBlueprint. Common Batch pipe issues to fix:
- Missing branch_pipe_code or referenced pipe that doesn't exist
- Wrong input types for batch processing (should be ListContent)
- Missing batch parameters configuration
"""

