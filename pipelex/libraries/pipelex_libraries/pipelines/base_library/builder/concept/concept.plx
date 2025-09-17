domain = "concept"
definition = "Build and process concepts for Pipelex bundles from signatures and drafts."

[concept]
ConceptStructureSpecBlueprint = "A concept blueprint with structure but without full implementation."
ConceptSpec = "A specification for a concept including its code, description, and a structure draft as plain text."
ConceptSpecBlueprint = "A structured blueprint for a concept."

[pipe.build_concept_blueprint]
type = "PipeSequence"
description = "Create a ConceptSpecBlueprint from a brief, existing concepts, and concept rules."
inputs = { concept_spec = "ConceptSpec"}
output = "ConceptSpecBlueprint"
steps = [
    { pipe = "spec_to_structure", result = "concept_spec_structures" },
    { pipe = "to_concept_blueprint", result = "concept_spec_blueprints" }
]

[pipe.to_concept_spec]
type = "PipeLLM"
description = "From the brief and one signature, propose a ConceptSpec (with a structure draft in plain text)."
inputs = { signature = "PipeSignature", brief = "builder.UserBrief" }
output = "ConceptSpec"
llm = "llm_to_engineer"
prompt_template = """
Return a ConceptSpec for the concept implied by the signature.

Brief:
@brief

Signature:
@signature

"""

[pipe.spec_to_structure]
type = "PipeLLM"
description = "Convert the ConceptSpec (with its structure draft) into a proper ConceptStructureSpecBlueprint."
inputs = { concept_spec = "ConceptSpec" }
output = "ConceptStructureSpecBlueprint"
multiple_output = true
llm = "llm_to_engineer"
prompt_template = """
Create a ConceptStructureSpecBlueprint from the ConceptSpec.
Please focus only on the structure.
The field "choices" is for Literal values or enums. When it is provided, the field "type" must be None. But the choices array cannot be empty.

The field "definition" IS NOT a structure. It is a general definition of the concept.
If the field "structure" is empty, return an empty list.

ConceptSpec:
@concept_spec
"""

[pipe.to_concept_blueprint]
type = "PipeFunc"
description = "Generate the final ConceptSpecBlueprint using the spec and structure manually."
inputs = { concept_spec = "ConceptSpec", concept_spec_structures = "ConceptStructureSpecBlueprint"}
output = "ConceptSpecBlueprint"
function_name = "create_concept_spec_blueprint"

