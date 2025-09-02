domain = "meta"
definition = "Meta domain is the domain of pipelines about pipelines"

[concept]
PipelineDraft = "Rough solution to create a pipeline"
PipelineDraftText = "Rough solution to create a pipeline in text format"
PipeDraft = "Rough solution to create a pipe"
ConceptBlueprint = "Details enabling to create a concept"
PipeBlueprint = "Details enabling to create a pipe"

[concept.PipelexBundleBlueprint]
definition = "Details enabling to create a pipeline"
structure = "PipelexBundleBlueprint"

[pipe]
[pipe.build_blueprint]
type = "PipeSequence"
definition = "Build a pipeline blueprint from natural language requirements"
inputs = { draft_pipeline_rules = "Text", build_pipeline_rules = "Text", create_structured_output_rules = "Text", requirements = "Text", pipeline_name = "Text", domain = "Text" }
output = "PipelexBundleBlueprint"
steps = [
    { pipe = "draft_pipeline_text", result = "pipeline_draft" },
    { pipe = "structure_blueprint", result = "pipeline_blueprint" },
]

[pipe.draft_pipeline_text]
type = "PipeLLM"
definition = "Generate a rough pipeline draft from natural language requirements"
inputs = { draft_pipeline_rules = "Text", create_structured_output_rules = "Text", requirements = "Text", pipeline_name = "Text", domain = "Text" }
output = "PipelineDraftText"
llm = "llm_to_pipelex"
prompt_template = """
You are a Pipelex pipeline architect. Build a pipeline draft text showing how we solve the problem.

@draft_pipeline_rules

Do create structured output for better concept representation.

@create_structured_output_rules
---
Name of the pipeline: $pipeline_name.

Domain: $domain.

Requirements: $requirements
"""

[pipe.structure_blueprint]
type = "PipeLLM"
definition = "Generate a pipeline blueprint from natural language requirements"
inputs = { build_pipeline_rules = "Text", pipeline_draft = "Text", pipeline_name = "Text", domain = "Text", requirements = "Text" }
output = "PipelexBundleBlueprint"
llm = "llm_to_pipelex"
prompt_template = """
You are a Pipelex pipeline architect. Build a structured pipeline blueprint from the provided pipeline draft text.

@build_pipeline_rules

@pipeline_draft

---
Name of the pipeline: $pipeline_name.

Domain: $domain.

Requirements: $requirements.
"""

