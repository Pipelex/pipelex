domain = "concept"
definition = "Build and process concepts for Pipelex bundles from signatures and drafts."

[concept]
ConceptStructureSpec = "A concept spec with structure but without full implementation."
ConceptSpec = "A specification for a concept including its code, description, and a structure draft as plain text."
ConceptSpecDraft = "A specification for a concept including its code, description, and a structure draft as plain text."

[pipe.build_concept_spec]
type = "PipeSequence"
definition = "Create a ConceptSpec from a brief, existing concepts, and concept rules."
inputs = { concept_spec_draft = "ConceptSpecDraft"}
output = "ConceptSpec"
steps = [
    { pipe = "spec_draft_to_structure", result = "concept_spec_structures" },
    { pipe = "spec_draft_to_concept_spec", result = "concept_spec" }
]

[pipe.spec_draft_to_structure]
type = "PipeLLM"
definition = "Convert the ConceptSpec (with its structure draft) into a proper ConceptStructureSpec."
inputs = { concept_spec_draft = "ConceptSpecDraft" }
output = "ConceptStructureSpec"
multiple_output = true
llm = "llm_to_engineer"
prompt_template = """
Create a ConceptStructureSpec from the ConceptSpecDraft.
Please focus only on the structure.

The field "definition" IS NOT a structure. It is a general definition of the concept.
If the field "structure" is empty, return an empty list.

ConceptSpecDraft:
@concept_spec_draft
"""

[pipe.spec_draft_to_concept_spec]
type = "PipeFunc"
definition = "Generate the final ConceptSpec using the spec and structure manually."
inputs = { concept_spec_draft = "ConceptSpecDraft", concept_spec_structures = "ConceptStructureSpec"}
output = "ConceptSpec"
function_name = "create_concept_spec"


# [pipe.fix_failing_concept]
# type = "PipeLLM"
# definition = "Fix a failing ConceptSpec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", failed_concept = "ConceptFailure" }
# output = "ConceptSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing ConceptSpec.

# Failing concept:
# @failed_concept.concept

# Error message:
# @failed_concept.error_message
# """

