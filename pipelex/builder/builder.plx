domain = "builder"
description = "Auto-generate a Pipelex bundle (concepts + pipes) from a short user brief."

[concept]
UserBrief = "A short, natural-language description of what the user wants."
PlanDraft = "Natural-language pipeline plan text describing sequences, inputs, outputs."
ConceptDrafts = "Textual draft of the concepts to create."
PipelexBundleSpec = "A Pipelex bundle spec."
BundleHeaderSpec = "A domain information object."
FlowDraft = "Draft of the flow of the pipeline."

[pipe]
[pipe.pipe_builder]
type = "PipeSequence"
description = "This pipe is going to be the entry point for the builder. It will take a UserBrief and return a PipelexBundleSpec."
inputs = { brief = "UserBrief" }
output = "builder.PipelexBundleSpec"
steps = [
    { pipe = "draft_the_plan", result = "plan_draft" },
    { pipe = "draft_the_concepts", result = "concept_drafts" },
    { pipe = "structure_concepts", result = "concept_specs" },
    { pipe = "draft_flow", result = "flow_draft" },
    { pipe = "review_flow", result = "prepared_flow" },
    { pipe = "design_pipe_signatures", result = "pipe_signatures" },
    { pipe = "write_bundle_header", result = "bundle_header_spec" },
    { pipe = "detail_pipe_spec", batch_over = "pipe_signatures", batch_as = "pipe_signature", result = "pipe_specs" },
    { pipe = "assemble_pipelex_bundle_spec", result = "pipelex_bundle_spec" }
]

[pipe.draft_the_plan]
type = "PipeLLM"
description = "Turn the brief into a pseudo-code plan describing controllers, pipes, their inputs/outputs."
inputs = { brief = "UserBrief" }
output = "PlanDraft"
model = "llm_to_engineer"
prompt = """
# Return a draft of a plan that narrates the pipeline as pseudo-steps (no code):
- For each pipe: state the pipe's description, inputs (by name using snake_case), and the output (by name using snake_case),
DO NOT indicate the inputs or output type. Just name them.
- Note where you will want structured outputs or inputs.

## Memory and flow:
- We have a memory system: the outputs of each pipe are added to the memory and can be used as inputs by subsequent pipes.
- The pipeline's initial inputs are added to the memory at the beginning.
- You don't need to flatten lists at the end or even in intermediate steps: our system manages branching and the memory flows into each branch.
- At the end of the pipeline, all the memory is delivered so there is not need to gather all the elements unless expressly requested by the brief.

## Available orchestration controllers:
- SEQUENCE: execute a sequence of pipes in order. It must reference the pipes it will execute.
- BATCH: concurrently executes THE SAME pipe on each element of a list taken from the memory. BATCH is a map operator: it transforms the input list in a new list of outputs, so if you want to apply several steps to the individual items, the batch MUST branch into a SEQUENCE of these steps.
- PARALLEL: concurrently executes DIFFERENT PIPES on any stuff from the memory. The outputs of each of the parallel pipes will be usable in the following steps.
- CONDITION: branches to a specific pipe, based on the evaluation of a conditional expression and according to an outcome map. There can also be a default outcome.

When describing the task of a pipe controller, be concise, don't detail all the sub-pipes but list the pipes they will use.

## Available pipe operators:
- LLM: uses a Vision/LLM to generate text or structured objects. It can generate single items or lists of items.
- IMG_GEN: uses an AI model to generate images from a prompt that is either the result of a previous step or part of the pipeline's original inputs. As the image generation prompt MUST be a text, you can plan to use an LLM step to write it.
- EXTRACT: extracts content from an image or a pdf, always outputs a list of pages (possibly a list of one page). Use it only when you need to use OCR or PDF extraction.

---

Now let's write the plan.

Make it narrative concise markdown format, no need to write tags such as "Description:", just write what you need to write.
Do not write any intro or outro, just write the plan.

What is important is to name the variables, from the initial inputs to the final outputs.
And the variable names must be consistent between the various steps.
In case of multiple items used as list in inputs or outputs, name them with a plural variable name when they are multiple, but then use the singular variable name when working with each item of the list.

It's also VERY IMPORTANT to list all the variables used by each pipe. All the memory is available, yes, so you can combine any inputs, but you must state which ones you will actually use in each pipe.

Apply the DRY principle: don't repeat yourself. if you have a task to apply several times, describe it as a dedicated pipe.

@brief

"""

[pipe.draft_the_concepts]
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

[pipe.structure_concepts]
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


[pipe.draft_flow]
type = "PipeLLM"
description = "Draft the flow of the pipeline."
inputs = { plan_draft = "PlanDraft", brief = "UserBrief", concept_specs = "concept.ConceptSpec" }
output = "builder.FlowDraft"
model = "llm_to_engineer"
system_prompt = """
You are a Senior engineer.
"""
prompt = """
# Your job is to structure the flow we have drafted based on a brief:

@brief

@plan_draft

{% if concept_specs %}
We have already defined the concepts you must use for the inputs and outputs of the pipes:
@concept_specs
And of course you still have the native concepts if required: Text, Image, PDF, Number, Page.
{% else %}
You can use the native concepts for the inputs and outputs of the pipes, as required: Text, Image, PDF, Number, Page.
{% endif %}

## For PipeOperators:

The flow you design must include the contracts for each of the PipeOperators to use: PipeLLM, PipeImgGen, PipeExtract.
Shape of the contract for PipeOperator is:
- type: PipeLLM | PipeImgGen | PipeExtract
- description: What the pipe does (string)
- inputs: Dictionary mapping variable names (snake_case) to concept codes (PascalCase), possibly with multiplicity brackets.
- result: Variable name for the pipe's result (snake_case). Can be referenced in subsequent pipes.
- output: Output concept code (PascalCase) possibly with multiplicity: 'Text' (single), 'Article[]' (list), 'Image[5]' (exactly 5).

## For the PipeControllers, which really define the flow, we need a more detailed contract, related to each type of controller:

### Start with the same contract as pipe operators above:
- type: PipeSequence | PipeParallel | PipeCondition | PipeBatch
- description: ditto
- inputs: ditto
- result: ditto
- output: ditto

### Then add the details for each type of controller:

**PipeSequence:**
- steps: List of sub-pipes to execute sequentially. Each step has: pipe (name of the pipe to execute), result (variable name).

**PipeParallel:**
- parallels: List of sub-pipes to execute concurrently.
- add_each_output: Boolean - include individual outputs in combined result.
- combined_output: Optional ConceptCode (PascalCase) for combined structure.

**PipeBatch:**
- branch_pipe_code: Pipe to apply to each item in the list (applied concurrently to all items).
- For PipeBatch, there must be at least one input which is a list, corresponding to input_list_name.
  That name is typically a plural noun like "ideas" or "images".
  And the concept corresponding to that input list must be multiple, using the [] notation,
  i.e. something like "Ideas[]" or "Images[]".
- input_list_name: List variable to iterate over (snake_case, plural).
- input_item_name: Name for individual items in each branch (snake_case, singular).

**PipeCondition:**
- jinja2_expression_template: Jinja2 expression to evaluate.
- outcomes: Mapping dict[str, str] of expression results to pipe codes.
- default_outcome: Fallback pipe_code or "fail"/"continue" if no match.

## More rules:
- For each pipe: give a unique snake_case pipe_code, based on a verb, and craft description of what the pipe does.
- When specifying the inputs and outputs of the pipes, you must indicate the concept associated to each variable name.
- The output concept of a PipeSequence must always be the same as the output concept of the last pipe in the sequence.
- Regarding PipeImgGen, which uses an AI model to generate images from a text prompt: as the image generation prompt MUST be a text, you must use a PipeLLM step to write the prompt, unless the prompt is part of the pipeline's initial inputs.
- When a variable comprises multiple items, use bracket notation along with the SINGULAR concept:
  - The concept is singular, like "Article" (not "Articles")
  - You can set output = "Article[]" to get a list of arbitrary length, or set output = "Article[5]" for exactly 5 items
  - Examples: output = "Text[]" (multiple texts), output = "Image[3]" (exactly 3 images), output = "Employee[]" (list of employees)
  - In particular, a PipeBatch always as an input which is a list on which it is batching, use indeterminate multiplicity for the list, i.e. "Concept[]".

## Flow:
- We have a memory system: the outputs of each pipe are added to the memory and can be used as inputs by subsequent pipes.
- The pipeline's initial inputs are added to the memory at the beginning.
- Do not bother with planning a final step that gathers all the elements unless it's clear from the brief that the user wants the pipe to do that.
- You don't need to flatten lists at the end or even in intermediate steps: our system manages branching and the memory flows into each branch.
- At the end of the pipeline, all the memory is delivered so there is not need to gather all the elements unless expressly requested by the brief.
- If you have a sequence which has only one step, then don't make that a sequence, make it a single pipe. Or check if you forgot to include another step maybe.
- If you're in a sequence and you are to apply a pipe to a previous output which is multiple, use a PipeBatch step.
- PipeBatch is a map operator: it transforms the input list in a new list of outputs, so if you want to apply several steps to the individual items, the branch_pipe_code MUST be a PipeSequence of these steps.
- Apply the DRY principle: don't repeat yourself. if you have a task to apply several times, make it a dedicated pipe you can use and reuse.

IMPORTANT: define the main pipe of the pipeline, i.e. unless it's a single pipe workflow, the main pipe is the overall orchestrator sequence of the whole pipeline. Give it a clear name, make it clear it's the main pipe in a "# Comment", but don't name it "main" or "orchestrator" or "pipeline", just state it's main in a comment.

If the main pipe has an input which is multiple (a list) then don't hesitate to batch over it.

At the end, recap the list of variables used, with a super concise recap of what they represent, also state their concept and multiplicity, and if the concept refines a native concept, state it too. Btw, by default, unstructured concepts refine Text, state it when it's the case.
"""


[pipe.review_flow]
type = "PipeLLM"
description = "Review a draft flow and make it consistent."
inputs = { flow_draft = "builder.FlowDraft", brief = "UserBrief" }
output = "builder.FlowDraft"
model = "llm_to_engineer"
system_prompt = """
You are a Senior engineer.
"""
prompt = """
Your job is to review a draft flow that was designed from a bried.

@brief

@flow_draft

Recap the flow by narrating the we have step by step, from the beginning to the end.
Is the flow consistent? Issues to watch out for:
- Do we have a main pipe appropriate to answer the brief? Otherwise we'll have to add one.
- Check that the inputs of the main pipe are consistent with the brief. For instance it should not require as input some variable which is to be generated by its own flow steps.
- If the main pipe has an input which is multiple (a list), are we correctly batching over it?
- Are there any missing variables or variable names that are not the expected names?
- PipeImgGen must take a single input which must be a text or a concept that refines text, if it's not the case, it needs fixing. For instance if the input is some structured concept, you'll have to add a PipeLLM step to write the prompt from the structured concept.

If the flow is consistent, state it in a declarative sentence like "The flow has been checked and is consistent:" and then copy the flow like you received it.

Otherwise, state that it was fixed like "The flow has been checked and fixed:" and then write the fixed flow. Your fixed flow must be flawless and consistent.
"""

[pipe.design_pipe_signatures]
type = "PipeLLM"
description = "Write the pipe signatures for the plan."
inputs = { prepared_flow = "builder.FlowDraft", brief = "UserBrief" }
output = "pipe_design.PipeSignature[]"
model = "llm_to_engineer"
system_prompt = """
You are a Senior engineer.
"""
prompt = """
# Your job is to structure the required PipeSignatures that make up the AI workflow we have prepared based on a brief.

@brief

@prepared_flow

## The PipeSignatures are like contracts for the pipes to build:
- For each pipe: give a unique snake_case pipe_code, based on a verb, and craft description of what the pipe does.
- Be clear which is the main pipe of the pipeline, don't write "main" in its pipe_code, but make it clear in its description.
- Contrary to the draft, now when specifying the inputs and outputs of the pipes, you must indicate the concept associated to each variable name.
- When a variable comprises multiple items, use bracket notation along with the SINGULAR concept:
  - The concept is singular, like "Article" (not "Articles")
  - You can set output = "Article[]" to get a list of arbitrary length, or set output = "Article[5]" for exactly 5 items
  - Examples: output = "Text[]" (multiple texts), output = "Image[3]" (exactly 3 images), output = "Employee[]" (list of employees)
- The output concept of a PipeSequence must always be the same as the output concept of the last pipe in the sequence.
- Pipe controllers (PipeSequence, PipeParallel, PipeCondition) depend on other pipes, so you must list these dependencies in the pipe_dependencies attribute.
- Regarding PipeImgGen, which uses an AI model to generate images from a text prompt: as the image generation prompt MUST be a text, you must use a PipeLLM step to write the prompt, unless it's part of the pipeline's initial inputs.


## Flow:
- We have a memory system: the outputs of each pipe are added to the memory and can be used as inputs by subsequent pipes.
- The pipeline's initial inputs are added to the memory at the beginning.
- Do not bother with planning a final step that gathers all the elements unless it's clear from the brief that the user wants the pipe to do that.
- You don't need to flatten lists at the end or even in intermediate steps: our system manages branching and the memory flows into each branch.
- At the end of the pipeline, all the memory is delivered so there is not need to gather all the elements unless expressly requested by the brief.
"""

[pipe.write_bundle_header]
type = "PipeLLM"
description = "Write the bundle header."
inputs = { brief = "UserBrief", pipe_signatures = "PipeSignature" }
output = "BundleHeaderSpec"
model = "llm_to_engineer"
prompt = """
Name and define the domain of this process:
@brief

@pipe_signatures

For example, if the brief is about generating and analyzing a compliance matrix out of a RFP,
the domain would be "rfp_compliance" and the description would be "Generating and analyzing compliance related to RFPs".
The domain name should be not more than 4 words, in snake_case.
For the description, be concise.
The main pipe is the one that will carry out the main task of the pipeline, it should be pretty obvious to identify.
"""

[pipe.assemble_pipelex_bundle_spec]
type = "PipeFunc"
description = "Compile the pipelex bundle spec."
inputs = { pipe_specs = "PipeSpec", concept_specs = "ConceptSpec", bundle_header_spec = "BundleHeaderSpec" }
output = "PipelexBundleSpec"
function_name = "assemble_pipelex_bundle_spec"

