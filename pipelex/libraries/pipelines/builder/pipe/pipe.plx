domain = "pipe"
definition = "Build and process pipes."

[concept]
PipeSignature = "Pseudo-Pipelex step: code, type, description, inputs, output, optional children refs."
PipeSpec = "A structured spec for a pipe (union)."
# Pipe controllers
PipeBatchSpec = "A structured spec for a pipe batch."
PipeConditionSpec = "A structured spec for a pipe condition."
PipeParallelSpec = "A structured spec for a pipe parallel."
PipeSequenceSpec = "A structured spec for a pipe sequence."
# Pipe operators
PipeFuncSpec = "A structured spec for a pipe func."
PipeImgGenSpec = "A structured spec for a pipe img gen."
PipeComposeSpec = "A structured spec for a pipe compose."
PipeLLMSpec = "A structured spec for a pipe llm."
PipeOcrSpec = "A structured spec for a pipe ocr."
PipeFailure = "Details of a single pipe failure during dry run."

[pipe]
# ────────────────────────────────────────────────────────────────────────────────
# NEW ENTRY POINT — takes PipeSignature[] + ConceptSpecs → PipeSpecs[]
# ────────────────────────────────────────────────────────────────────────────────
[pipe.create_pipes_from_signatures]
type = "PipeSequence"
description = "PipeSignature[] + ConceptSpecs → PipeSpecs[] (linked & ready)."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "Dynamic"
steps = [
    { pipe = "generate_pipe_spec", result = "pipe_spec" },
    { pipe = "compile_one_signature_spec", result = "compiled_spec" },
]

[pipe.generate_pipe_spec]
type = "PipeLLM"
description = "Generate a PipeSpec from a PipeSignature."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeSpec"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeSpec for this signature.

Signature:
@pipe_signature

and here are the existing concepts:
@concept_specs

The inputs keys should be snake_case.
The values should be a concept code in PascalCase.
"""

# ────────────────────────────────────────────────────────────────────────────────
# CORE: signature → route to spec emitter
# ────────────────────────────────────────────────────────────────────────────────
[pipe.compile_one_signature_spec]
type = "PipeCondition"
description = "Route by signature.type to the correct spec emitter."
inputs = { pipe_signature = "PipeSignature", concept_specs = "ConceptSpec", pipe_spec = "PipeSpec" }
output = "Dynamic"
expression = "pipe_signature.type"

[pipe.compile_one_signature_spec.pipe_map]
PipeSequence  = "emit_sequence_from_signature"
PipeParallel  = "emit_parallel_from_signature"
PipeCondition = "emit_condition_from_signature"
PipeBatch     = "emit_batch_from_signature"
PipeLLM       = "emit_llm_from_signature"
PipeOcr       = "emit_ocr_from_signature"
PipeImgGen    = "emit_imggen_from_signature"
PipeCompose   = "emit_compose_from_signature"
PipeFunc      = "emit_func_from_signature"

# ────────────────────────────────────────────────────────────────────────────────
# EMITTERS — one per pipe type, all using the same minimal contract
# (Optionally, emitters could be extended later to read from concept_index.)
# ────────────────────────────────────────────────────────────────────────────────

[pipe.emit_sequence_from_signature]
type = "PipeLLM"
description = "Build a PipeSequenceSpec from the signature (children referenced by code)."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec", pipe_spec = "PipeSpec" }
output = "PipeSequenceSpec"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeSequenceSpec for this signature.
The Pipe sequence NEEDS to have at least one step.
Orchestrate all the necessary steps to achieve the goal of the pipe.

Signature:
@pipe_signature

Here is the base PipeSpec:
@pipe_spec

And here are the concepts you can use:
@concept_specs
"""

[pipe.emit_parallel_from_signature]
type = "PipeLLM"
description = "Build a PipeParallelSpec from the signature."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec", pipe_spec = "PipeSpec" }
output = "PipeParallelSpec"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeParallelSpec for this signature.

Signature:
@pipe_signature

Here is the base PipeSpec:
@pipe_spec

And here are the concepts you can use:
@concept_specs
"""

[pipe.emit_condition_from_signature]
type = "PipeLLM"
description = "Build a PipeConditionSpec from the signature (provide expression/pipe_map consistent with children)."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec", pipe_spec = "PipeSpec" }
output = "PipeConditionSpec"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeConditionSpec for this signature.

Signature:
@pipe_signature

Here is the base PipeSpec:
@pipe_spec

And here are the concepts you can use:
@concept_specs
"""

[pipe.emit_batch_from_signature]
type = "PipeLLM"
description = "Build a PipeBatchSpec from the signature (choose branch_pipe_code/params)."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec", pipe_spec = "PipeSpec" }
output = "PipeBatchSpec"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeBatchSpec for this signature.

Signature:
@pipe_signature

Here is the base PipeSpec:
@pipe_spec

And here are the concepts you can use:
@concept_specs
"""

[pipe.emit_llm_from_signature]
type = "PipeLLM"
description = "Build a PipeLLMSpec from the signature."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec", pipe_spec = "PipeSpec" }
output = "PipeLLMSpec"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeLLMSpec for this signature.

THe prompt is the field "prompt_template" in the PipeLLMSpec.
Signature:
@pipe_signature

Here is the base PipeSpec:
@pipe_spec

And here are the concepts you can use:
@concept_specs
"""

[pipe.emit_ocr_from_signature]
type = "PipeLLM"
description = "Build a PipeOcrSpec from the signature."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec", pipe_spec = "PipeSpec" }
output = "PipeOcrSpec"
prompt_template = """
Return a PipeOcrSpec for this signature.

VERY IMPORTANT: THE INPUT OF THE PIPEOCR MUST BE either an image or a pdf or a concept which refines one of them.
Signature:
@pipe_signature

Here is the base PipeSpec:
@pipe_spec

And here are the concepts you can use:
@concept_specs
"""

[pipe.emit_imggen_from_signature]
type = "PipeLLM"
description = "Build a PipeImgGenSpec from the signature."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec", pipe_spec = "PipeSpec" }
output = "PipeImgGenSpec"
prompt_template = """
Return a PipeImgGenSpec for this signature.
The inputs for the image has to be only:
input_name : prompt
concept : A concept that refines Text. It should be text
The output concept should be a concept in Pascal case that refines Image.
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

Here is the base PipeSpec:
@pipe_spec

And here are the concepts you can use:
@concept_specs
"""

[pipe.emit_compose_from_signature]
type = "PipeLLM"
description = "Build a PipeComposeSpec from the signature."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec", pipe_spec = "PipeSpec" }
output = "PipeComposeSpec"
prompt_template = """
Return a PipeComposeSpec for this signature.

Signature:
@pipe_signature

Here is the base PipeSpec:
@pipe_spec

And here are the concepts you can use:
@concept_specs
"""

[pipe.emit_func_from_signature]
type = "PipeLLM"
description = "Build a PipeFuncSpec from the signature."
inputs = { pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec", pipe_spec = "PipeSpec" }
output = "PipeFuncSpec"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeFuncSpec for this signature.

Signature:
@pipe_signature

Here is the base PipeSpec:
@pipe_spec

And here are the concepts you can use:
@concept_specs
"""

# ────────────────────────────────────────────────────────────────────────────────
# PIPE FIXERS — one per pipe type, all fixing specific pipe type issues
# ────────────────────────────────────────────────────────────────────────────────

[pipe.fix_failing_pipe]
type = "PipeCondition"
description = "Route to specific pipe fixer based on the failing pipe type."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "Dynamic"
expression = "failed_pipe.pipe.type"

[pipe.fix_failing_pipe.pipe_map]
PipeLLM = "fix_failing_llm_pipe"
PipeImgGen = "fix_failing_imggen_pipe"
PipeOcr = "fix_failing_ocr_pipe"
PipeFunc = "fix_failing_func_pipe"
PipeCompose = "fix_failing_compose_pipe"
PipeSequence = "fix_failing_sequence_pipe"
PipeParallel = "fix_failing_parallel_pipe"
PipeCondition = "fix_failing_condition_pipe"
PipeBatch = "fix_failing_batch_pipe"

[pipe.fix_failing_llm_pipe]
type = "PipeLLM"
description = "Fix a failing PipeLLM spec based on its specific error."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "PipeLLMSpec"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeLLM spec.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeLLMSpec. Common LLM pipe issues to fix:
- Missing input variables in the pipe inputs that are referenced in prompt_template
- Incorrect variable names in prompt templates (use $ for inline, @ for blocks)
- Wrong concept types for inputs/outputs
- Missing llm configuration
- Invalid prompt template syntax
"""

[pipe.fix_failing_imggen_pipe]
type = "PipeLLM"
description = "Fix a failing PipeImgGen spec based on its specific error."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "PipeImgGenSpec"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeImgGen spec.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeImgGenSpec. Common ImgGen pipe issues to fix:
- Missing or incorrect prompt input (should be text concept)
- Wrong img_gen_prompt_var_name (should be None or "prompt")
- Invalid img_gen choice
- Missing required inputs for dynamic prompt generation
"""

[pipe.fix_failing_ocr_pipe]
type = "PipeLLM"
description = "Fix a failing PipeOcr spec based on its specific error."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "PipeOcrSpec"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeOcr spec.

VERY IMPORTANT: THE INPUT OF THE PIPEOCR must be either an image or a pdf or a concept which refines one of them.
Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeOcrSpec. Common OCR pipe issues to fix:
- Input must be of type Image or PDF
- Output should typically be Page (native concept)
- Missing or incorrect input concept types
"""

[pipe.fix_failing_func_pipe]
type = "PipeLLM"
description = "Fix a failing PipeFunc spec based on its specific error."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "PipeFuncSpec"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeFunc spec.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeFuncSpec. Common Func pipe issues to fix:
- Missing or incorrect function_name
- Wrong input/output concept types for the function
- Function not available in registry
"""

[pipe.fix_failing_compose_pipe]
type = "PipeLLM"
description = "Fix a failing PipeCompose spec based on its specific error."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "PipeComposeSpec"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeCompose spec.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeComposeSpec. Common compose pipe issues to fix:
- Invalid Jinja2 template syntax
- Missing input variables referenced in template
- Wrong concept types for inputs/outputs
"""

[pipe.fix_failing_sequence_pipe]
type = "PipeLLM"
description = "Fix a failing PipeSequence spec based on its specific error."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "PipeSequenceSpec"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeSequence spec.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeSequenceSpec. Common Sequence pipe issues to fix:
- Missing input variables needed by sub-pipes in steps
- Referenced pipe codes in steps that don't exist
- Circular dependencies in step order
- Wrong result names in steps
"""

[pipe.fix_failing_parallel_pipe]
type = "PipeLLM"
description = "Fix a failing PipeParallel spec based on its specific error."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "PipeParallelSpec"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeParallel spec.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeParallelSpec. Common Parallel pipe issues to fix:
- Missing input variables needed by parallel sub-pipes
- Referenced pipe codes that don't exist
- Incompatible output types from parallel branches
"""

[pipe.fix_failing_condition_pipe]
type = "PipeLLM"
description = "Fix a failing PipeCondition spec based on its specific error."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "PipeConditionSpec"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeCondition spec.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeConditionSpec. Common Condition pipe issues to fix:
- Invalid expression or expression_template syntax
- Referenced pipe codes in pipe_map that don't exist
- Missing input variables referenced in expression
- Incompatible output types from different condition branches
"""

[pipe.fix_failing_batch_pipe]
type = "PipeLLM"
description = "Fix a failing PipeBatch spec based on its specific error."
inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_pipe = "PipeFailure" }
output = "PipeBatchSpec"
llm = "llm_to_engineer"
prompt_template = """
Fix this failing PipeBatch spec.

Failing pipe:
@failed_pipe.pipe

Error message:
@failed_pipe.error_message

Please provide only the corrected PipeBatchSpec. Common Batch pipe issues to fix:
- Missing branch_pipe_code or referenced pipe that doesn't exist
- Wrong input types for batch processing (should be ListContent)
- Missing batch parameters configuration
"""

