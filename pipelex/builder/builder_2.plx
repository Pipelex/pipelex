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
output = "PipelexBundleSpec"
steps = [
    { pipe = "draft_the_plan_2", result = "plan_draft" },
    # { pipe = "draft_the_concepts", result = "concept_drafts" },
    # { pipe = "structure_concepts", result = "concept_specs" },
    # { pipe = "design_pipe_signatures", result = "pipe_signatures" },
    # { pipe = "detail_pipe_spec", batch_over = "pipe_signatures", batch_as = "pipe_signature", result = "pipe_specs" },
    # { pipe = "write_bundle_header", result = "bundle_header_spec" },
    # { pipe = "assemble_pipelex_bundle_spec", result = "pipelex_bundle_spec" }
]

[pipe.draft_the_plan_2]
type = "PipeLLM"
description = "Turn the brief into a pseudo-code plan describing controllers, pipes, their inputs/outputs."
inputs = { brief = "UserBrief" }
output = "PlanDraft"
model = "llm_to_engineer"
prompt = """
Return a draft of a plan that narrates the pipeline as pseudo-steps (no code):
- Be clear which is the main pipe of the pipeline, don't write "main" in its name, but make it clear in its description.
- For each pipe: state the pipe's description, inputs (by name using snake_case), and the output (by name using snake_case),
DO NOT indicate the inputs or output type. Just name them.
- Note where you will want structured outputs or inputs.
- Do not bother with planning a final step that gathers all the elements unless it's clear from the brief that the user wants the pipe to do that.
- We have a memory system: the outputs of each pipe are added to the memory and can be used as inputs by subsequent pipes.
- The pipeline's initial inputs are added to the memory at the beginning.
- At the end of the pipeline, all the memory is delivered so there is not need to gather all the elements unless expressly requested by the brief.

Available orchestration controllers:
- PipeSequence: execute a sequence of pipes in order. It must reference the pipes it will execute.
- PipeBatch: concurrently executes THE SAME pipe on each element of a list taken from the memory.
- PipeParallel: concurrently executes DIFFERENT PIPES on any stuff from the memory.
The outputs of each of the parallel pipes will be usable in the following steps.
- PipeCondition: branches to a specific pipe, based on the evaluation of a conditional expression and according to an outcome map.
There can also be a default outcome.

When describing the task of a pipe controller, be concise, don't detail all the sub-pipes but list the pipes they will use.

Available pipe operators:
- PipeLLM: uses a Vision/LLM to generate text or structured objects. It can be single items or lists of items.
- PipeImgGen: uses an AI model to generate images from a prompt that is either the result of a previous step or the pipeline's original inputs.
- PipeExtract: extracts text from an image or a pdf, always outputs a list of pages (can be a list of one page).

---

Now let's write the plan.

Make it narrative concise markdown format, no need to write tags such as "Description:", just write what you need to write.
Do not write any intro or outro, just write the plan.

What is important is to name the variables, from the initial inputs to the final outputs.
And the variable names must be consistent between the various steps.
In case of multiple items used as list in inputs or outputs, name them with a plural variable name when they are multiple,
but then use the singular variable name when working with each item of the list.

It's also VERY IMPORTANT to list all the variables used by each pipe. All the memory is available, yes, so you can combine, any input, but you must state which ones you will use.

Apply the DRY principle: don't repeat yourself. if you have a task to apply several times, describe it as a dedicated pipe.

@brief
"""