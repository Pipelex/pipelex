domain = "concept"
definition = "Build and process concepts for Pipelex bundles from signatures and drafts."

[concept]
ConceptStructureSpec = "A concept spec with structure but without full implementation."
ConceptSpec = "A specification for a concept including its code, description, and a structure draft as plain text."

[pipe.build_concept_spec]
type = "PipeSequence"
description = "Create a ConceptSpec from a brief, existing concepts, and concept rules."
inputs = { concept_spec = "ConceptSpec"}
output = "ConceptSpec"
steps = [
    { pipe = "spec_to_structure", result = "concept_spec_structures" },
    { pipe = "to_concept_spec", result = "concept_spec" }
]

[pipe.spec_to_structure]
type = "PipeLLM"
description = "Convert the ConceptSpec (with its structure draft) into a proper ConceptStructureSpec."
inputs = { concept_spec = "ConceptSpec" }
output = "ConceptStructureSpec"
multiple_output = true
llm = "llm_to_engineer"
prompt_template = """
Create a ConceptStructureSpec from the ConceptSpec.
Please focus only on the structure.

The field "definition" IS NOT a structure. It is a general definition of the concept.
If the field "structure" is empty, return an empty list.

ConceptSpec:
@concept_spec
"""

[pipe.to_concept_spec]
type = "PipeFunc"
description = "Generate the final ConceptSpec using the spec and structure manually."
inputs = { concept_spec = "ConceptSpec", concept_spec_structures = "ConceptStructureSpec"}
output = "ConceptSpec"
function_name = "create_concept_spec"

