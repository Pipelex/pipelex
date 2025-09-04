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
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeBlueprint for this signature.

Signature:
@pipe_signature

and here are the existing concepts:
@concept_spec_blueprints
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
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeSequenceSpecBlueprint for this signature.

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
structuring_method = "preliminary_text"
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
structuring_method = "preliminary_text"
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
structuring_method = "preliminary_text"
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
structuring_method = "preliminary_text"
llm = "llm_to_engineer"
prompt_template = """
Return a PipeLLMSpecBlueprint for this signature.

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
structuring_method = "preliminary_text"
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
structuring_method = "preliminary_text"
prompt_template = """
Return a PipeImgGenSpecBlueprint for this signature.

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
structuring_method = "preliminary_text"
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
structuring_method = "preliminary_text"
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

