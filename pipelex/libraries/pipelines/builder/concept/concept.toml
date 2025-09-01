domain = "concept"
definition = "Build and process concepts for Pipelex bundles from signatures and drafts."

[concept]
UserBrief = "A short, natural-language description of what the user wants."
ConceptSpec = "A specification for a concept including its code, description, and a structure draft as plain text."
ConceptStructureBlueprint = "A concept blueprint with structure but without full implementation."
ConceptBlueprint = "A structured blueprint for a concept."

[pipe.build_concept_blueprint]
type = "PipeSequence"
description = "Create a ConceptBlueprint from a brief, existing concepts, and concept rules."
inputs = { concept_spec = "ConceptSpec"}
output = "ConceptBlueprint"
steps = [
    { pipe = "spec_to_structure", result = "concept_structure" },
    { pipe = "to_concept_blueprint", result = "concept_blueprints" }
]

[pipe.to_concept_spec]
type = "PipeLLM"
description = "From the brief and one signature, propose a ConceptSpec (with a structure draft in plain text)."
inputs = { signature = "PipeSignature", brief = "UserBrief" }
output = "ConceptSpec"
llm = "llm_to_engineer"
structuring_method = "preliminary_text"
prompt_template = """
Return a ConceptSpec for the concept implied by the signature.

Brief:
@brief

Signature:
@signature

"""

[pipe.spec_to_structure]
type = "PipeLLM"
description = "Convert the ConceptSpec (with its structure draft) into a proper ConceptStructureBlueprint."
inputs = { concept_spec = "ConceptSpec" }
output = "ConceptStructureBlueprint"
multiple_output = true
llm = "llm_to_engineer"
structuring_method = "preliminary_text"
prompt_template = """
Create a ConceptStructureBlueprint from the ConceptSpec.
ConceptSpec:
@concept_spec

Please focus only on the structure.
The field "choices" is for Literal values or enums. When it is provided, the field "type" must be None. But the choices array cannot be empty.

"""

[pipe.to_concept_blueprint]
type = "PipeLLM"
description = "Generate the final ConceptBlueprint using the spec, structure, and existing concept context."
inputs = { concept_spec = "ConceptSpec", concept_structure = "ConceptStructureBlueprint"}
output = "ConceptBlueprint"
structuring_method = "preliminary_text"
prompt_template = """
Create a ConceptBlueprint using the ConceptSpec and ConceptStructureBlueprint.

ConceptSpec:
@concept_spec

Structure:
@concept_structure

The output structure should be a valid ConceptStructureBlueprint object.
"""

