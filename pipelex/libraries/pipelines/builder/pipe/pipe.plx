domain = "pipe"
definition = "Build and process pipes."

[concept]
PipeSignature = "Pseudo-Pipelex step: code, type, description, inputs, output, optional children refs."
PipeBlueprint = "A structured blueprint for a pipe (union)."
# New/clarified concepts for this variant
ConceptBlueprint = "A reusable PipeBlueprint identified by a unique code."
ConceptIndex = "Map<string code, ConceptBlueprint>."

# Pipe controllers
PipeBatchBlueprint = "A structured blueprint for a pipe batch."
PipeConditionBlueprint = "A structured blueprint for a pipe condition."
PipeParallelBlueprint = "A structured blueprint for a pipe parallel."
PipeSequenceBlueprint = "A structured blueprint for a pipe sequence."
# Pipe operators
PipeFuncBlueprint = "A structured blueprint for a pipe func."
PipeImgGenBlueprint = "A structured blueprint for a pipe img gen."
PipeJinja2Blueprint = "A structured blueprint for a pipe jinja2."
PipeLLMBlueprint = "A structured blueprint for a pipe llm."
PipeOcrBlueprint = "A structured blueprint for a pipe ocr."

[pipe]
# ────────────────────────────────────────────────────────────────────────────────
# NEW ENTRY POINT — takes PipeSignature[] + ConceptBlueprints → PipeBlueprint[]
# ────────────────────────────────────────────────────────────────────────────────
[pipe.create_pipes_from_signatures]
type = "PipeSequence"
description = "PipeSignature[] + ConceptBlueprints → PipeBlueprint[] (linked & ready)."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint" }
output = "Dynamic"
steps = [
    { pipe = "generate_pipe_blueprint", result = "pipe_blueprint" },
    { pipe = "compile_one_signature_blueprint", result = "compiled_blueprints" },
]

[pipe.generate_pipe_blueprint]
type = "PipeLLM"
description = "Generate a PipeBlueprint from a PipeSignature."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint" }
output = "PipeBlueprint"
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeBlueprint for this signature.

Signature:
@pipe_signature

and here are the existing concepts:
@concept_blueprints
"""

# ────────────────────────────────────────────────────────────────────────────────
# CORE: signature → route to blueprint emitter (unchanged)
# ────────────────────────────────────────────────────────────────────────────────
[pipe.compile_one_signature_blueprint]
type = "PipeCondition"
description = "Route by signature.type to the correct blueprint emitter."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
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
description = "Build a PipeSequenceBlueprint from the signature (children referenced by code)."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeSequenceBlueprint"
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeSequenceBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_blueprints
"""

[pipe.emit_parallel_from_signature]
type = "PipeLLM"
description = "Build a PipeParallelBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeParallelBlueprint"
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeParallelBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_blueprints
"""

[pipe.emit_condition_from_signature]
type = "PipeLLM"
description = "Build a PipeConditionBlueprint from the signature (provide expression/pipe_map consistent with children)."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeConditionBlueprint"
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeConditionBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_blueprints
"""

[pipe.emit_batch_from_signature]
type = "PipeLLM"
description = "Build a PipeBatchBlueprint from the signature (choose branch_pipe_code/params)."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeBatchBlueprint"
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeBatchBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_blueprints
"""

[pipe.emit_llm_from_signature]
type = "PipeLLM"
description = "Build a PipeLLMBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeLLMBlueprint"
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeLLMBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_blueprints
"""

[pipe.emit_ocr_from_signature]
type = "PipeLLM"
description = "Build a PipeOcrBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeOcrBlueprint"
structuring_method = "preliminary_text"
prompt_template = """
Return a PipeOcrBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_blueprints
"""

[pipe.emit_imggen_from_signature]
type = "PipeLLM"
description = "Build a PipeImgGenBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeImgGenBlueprint"
structuring_method = "preliminary_text"
prompt_template = """
Return a PipeImgGenBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_blueprints
"""

[pipe.emit_jinja_from_signature]
type = "PipeLLM"
description = "Build a PipeJinja2Blueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeJinja2Blueprint"
structuring_method = "preliminary_text"
prompt_template = """
Return a PipeJinja2Blueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_blueprints
"""

[pipe.emit_func_from_signature]
type = "PipeLLM"
description = "Build a PipeFuncBlueprint from the signature."
inputs = { pipe_signature = "PipeSignature", concept_blueprints = "ConceptBlueprint", pipe_blueprint = "PipeBlueprint" }
output = "PipeFuncBlueprint"
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeFuncBlueprint for this signature.

Signature:
@pipe_signature

Here is the base PipeBlueprint:
@pipe_blueprint

And here are the concepts you can use:
@concept_blueprints
"""

