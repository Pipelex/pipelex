domain = "builder"
description = "Auto-generate a Pipelex bundle (concepts + pipes) from a short user brief."

# ────────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────────
[pipe]
[pipe.pipe_builder_2]
type = "PipeSequence"
description = "This pipe is going to be the entry point for the builder. It will take a UserBrief and return a PipelexBundleSpec."
inputs = { brief = "UserBrief" }
output = "builder.PipelexBundleSpec"
# output = "pipe_design.PipeSignature[]"
steps = [
    { pipe = "draft_the_plan_2", result = "plan_draft" },
    { pipe = "draft_the_concepts_2", result = "concept_drafts" },
    { pipe = "structure_concepts_2", result = "concept_specs" },
    { pipe = "design_pipe_signatures_2", result = "pipe_signatures" },
    { pipe = "write_bundle_header", result = "bundle_header_spec" },
    { pipe = "detail_pipe_spec_2", batch_over = "pipe_signatures", batch_as = "pipe_signature", result = "pipe_specs" },
    { pipe = "assemble_pipelex_bundle_spec", result = "pipelex_bundle_spec" }
]

[pipe.draft_the_plan_2]
type = "PipeLLM"
description = "Turn the brief into a pseudo-code plan describing controllers, pipes, their inputs/outputs."
inputs = { brief = "UserBrief" }
output = "PlanDraft"
model = "llm_to_engineer"
prompt = """
# Return a draft of a plan that narrates the pipeline as pseudo-steps (no code):
- Be clear which is the main pipe of the pipeline, don't write "main" in its name, but make it clear in its description.
- For each pipe: state the pipe's description, inputs (by name using snake_case), and the output (by name using snake_case),
DO NOT indicate the inputs or output type. Just name them.
- Note where you will want structured outputs or inputs.

## Memory and flow:
- Do not bother with planning a final step that gathers all the elements unless it's clear from the brief that the user wants the pipe to do that.
- We have a memory system: the outputs of each pipe are added to the memory and can be used as inputs by subsequent pipes.
- The pipeline's initial inputs are added to the memory at the beginning.
- At the end of the pipeline, all the memory is delivered so there is not need to gather all the elements unless expressly requested by the brief.
- You don't need to flatten lists at the end or even in intermediate steps: our system manages branching and the memory flows into each branch.

## Available orchestration controllers:
- SEQUENCE: execute a sequence of pipes in order. It must reference the pipes it will execute.
- BATCH: concurrently executes THE SAME pipe on each element of a list taken from the memory.
- PARALLEL: concurrently executes DIFFERENT PIPES on any stuff from the memory.
The outputs of each of the parallel pipes will be usable in the following steps.
- CONDITION: branches to a specific pipe, based on the evaluation of a conditional expression and according to an outcome map.
There can also be a default outcome.

When describing the task of a pipe controller, be concise, don't detail all the sub-pipes but list the pipes they will use.

## Available pipe operators:
- LLM: uses a Vision/LLM to generate text or structured objects. It can be single items or lists of items.
- IMGGEN: uses an AI model to generate images from a prompt that is either the result of a previous step or the pipeline's original inputs.
- EXTRACT: extracts text from an image or a pdf, always outputs a list of pages (can be a list of one page).

---

Now let's write the plan.

Make it narrative concise markdown format, no need to write tags such as "Description:", just write what you need to write.
Do not write any intro or outro, just write the plan.

What is important is to name the variables, from the initial inputs to the final outputs.
And the variable names must be consistent between the various steps.
In case of multiple items used as list in inputs or outputs, name them with a plural variable name when they are multiple, but then use the singular variable name when working with each item of the list.

It's also VERY IMPORTANT to list all the variables used by each pipe. All the memory is available, yes, so you can combine, any input, but you must state which ones you will use.

Apply the DRY principle: don't repeat yourself. if you have a task to apply several times, describe it as a dedicated pipe.

@brief
"""

[pipe.draft_the_concepts_2]
type = "PipeLLM"
description = "Interpret the draft of a plan to create an AI pipeline, and define the needed concepts."
inputs = { plan_draft = "PlanDraft", brief = "UserBrief" }
output = "ConceptDrafts"
model = "llm_to_engineer"
prompt = """
We are working on writing an AI pipeline to fulfill this brief:
@brief

We have already written a plan for the pipeline. It's built using pipes, each with its own inputs (one or more) and output (single).
Your job is to clarify the different concepts used in the plan.

Variables are snake_case and concepts are PascalCase.

We want clear concepts but we don't want  too many concepts. If a concept can be reused in the pipeline, it's the same concept.
For instance:
- If you have a "FlowerDescription" concept, then it can be used for rose_description, tulip_description, beautiful_flower_description, dead_flower_description, etc.
- DO NOT define concepts that include adjectives: "LongArticle" is wrong, "Article" is right.
- DO NOT include circumstances in the concept description:
  "ArticleAboutApple" is wrong, "Article" is right.
  "CounterArgument" is wrong, "Argument" is right.
- Concepts are always expressed as singular nouns, even if we're to use them as a list:
  for instance, define the concept as "Article" not "Articles", "Employee" not "Employees".
  If we need multiple items, we'll indicate it elsewhere so you don't bother with it here.
- Provide a concise description for each concept

If the concept can be expressed as a text, image, pdf, number, or page:
- Name the concept, define it and just write "refines: Text", "refines: PDF", or "refines: Image" etc.
- No need to define its structure
Else, if you need structure for your concept, draft its structure:
- field name in snake_case
- description:
  - description: the description of the field, in natural language
  - type: the type of the field (text, integer, boolean, number, date)
  - required: add required = true if the field is required (otherwise, leave it empty)
  - default_value: the default value of the field

@plan_draft

DO NOT redefine native concepts such as: Text, Image, PDF, Number, Page. if you need one of these, they already exist so you should NOT REDEFINE THEM.

Do not write any intro or outro, do not mention the brief or the plan draft, just write the concept drafts.
List the concept drafts in Markdown format with a heading 3 for each, e.g. `### Concept FooBar`.
"""

[pipe.structure_concepts_2]
type = "PipeLLM"
description = "Structure the concept definitions."
inputs = { concept_drafts = "ConceptDrafts" }
output = "concept.ConceptSpec[]"
model = "llm_to_engineer"
system_prompt = """
You are an expert at data extraction and json formatting.
"""
prompt = """
@concept_drafts
"""


[pipe.design_pipe_signatures_2]
type = "PipeLLM"
description = "Write the pipe signatures for the plan."
inputs = { plan_draft = "PlanDraft", brief = "UserBrief", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeSignature[]"
model = "llm_to_engineer"
system_prompt = """
You are a Senior engineer.
"""
prompt = """
# Your job is to structure the required PipeSignatures that make up the AI workflow we have drafted based on a brief.

@brief

@plan_draft

{% if concept_specs %}
We have already defined the concepts you must use for the inputs and outputs of the pipes:
@concept_specs
And of course you still have the native concepts if required: Text, Image, PDF, Number, Page.
{% else %}
You can use the native concepts for the inputs and outputs of the pipes, as required: Text, Image, PDF, Number, Page.
{% endif %}

## The PipeSignatures are like contracts for the pipes to build:
- For each pipe: give a unique snake_case pipe_code, based on a verb, and craft description of what the pipe does.
- Be clear which is the main pipe of the pipeline, don't write "main" in its pipe_code, but make it clear in its description.
- Contrary to the draft, now when specifying the inputs and outputs of the pipes, you must indicate the concept associated to each variable name.
- When a variable comprises multiple items, use bracket notation along with the SINGULAR concept:
  - The concept is singular, like "Article" (not "Articles")
  - You can set output = "Article[]" to get a list of arbitrary length, or set output = "Article[5]" for exactly 5 items
  - Examples: output = "Text[]" (multiple texts), output = "Image[3]" (exactly 3 images), output = "Employee[]" (list of employees)
- The output concept of a pipe sequence must always be the same as the output concept of the last pipe in the sequence.

## Memory and flow:
- Do not bother with planning a final step that gathers all the elements unless it's clear from the brief that the user wants the pipe to do that.
- We have a memory system: the outputs of each pipe are added to the memory and can be used as inputs by subsequent pipes.
- The pipeline's initial inputs are added to the memory at the beginning.
- At the end of the pipeline, all the memory is delivered so there is not need to gather all the elements unless expressly requested by the brief.
- You don't need to flatten lists at the end or even in intermediate steps: our system manages branching and the memory flows into each branch.

## DRY principle:
- Apply the DRY principle: don't repeat yourself. if you have a task to apply several times, make it a dedicated pipe you can use and reuse.
- If you're in a sequence and you are to apply that pipe to a previous output which is multiple, use the batch_over/batch_as attributes in that step to trigger the BATCH mechanism.
- You must never include more than one batching step in the same pipe sequence. Instead, you must create a separate pipe sequence that will be run for each batched element.
"""