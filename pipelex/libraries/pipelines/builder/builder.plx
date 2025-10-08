domain = "builder"
description = "Auto-generate a Pipelex bundle (concepts + pipes) from a short user brief."

[concept]
UserBrief = "A short, natural-language description of what the user wants."
PlanDraft = "Natural-language pipeline plan text describing sequences, inputs, outputs."
ConceptDrafts = "Textual draft of the concepts to create."
PipelexBundleSpec = "A Pipelex bundle spec."
ValidationResult = "Status (success or failure) and details of the validation failure if applicable."
# PipeFailure = "Details of a single pipe failure during dry run."
# DryRunResult = "A result of a dry run of a pipelex bundle spec."
DomainInformation = "A domain information object."

# ────────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────────
[pipe]
[pipe.pipe_builder]
type = "PipeSequence"
description = "This pipe is going to be the entry point for the builder. It will take a UserBrief and return a PipelexBundleSpec."
inputs = { brief = "UserBrief" }
output = "PipelexBundleSpec"
steps = [
    { pipe = "draft_the_plan", result = "plan_draft" },
    { pipe = "draft_the_concepts", result = "concept_drafts" },
    { pipe = "structure_concepts", result = "concept_specs" },
    { pipe = "design_pipe_signatures", result = "pipe_signatures" },
    { pipe = "detail_pipe_spec", batch_over = "pipe_signatures", batch_as = "pipe_signature", result = "pipe_specs" },
    { pipe = "pipe_builder_domain_information", result = "domain_information" },
    { pipe = "assemble_pipelex_bundle_spec", result = "pipelex_bundle_spec" }
]

[pipe.pipe_builder_domain_information]
type = "PipeLLM"
description = "Turn the brief into a DomainInformation object."
inputs = { brief = "UserBrief" }
output = "DomainInformation"
model = "llm_to_engineer"
prompt = """
Name and define the domain of this process:
@brief

For example, if the brief is about generating and analyzing a compliance matrix out of a RFP,
the domain would be "rfp_compliance" and the definition would be "Generating and analyzing compliance related to RFPs".
The domain name should be not more than 4 words, in snake_case.
For the definition, be concise.
"""

[pipe.draft_the_plan]
type = "PipeLLM"
description = "Turn the brief into a pseudo-code plan describing controllers, pipes, their inputs/outputs."
inputs = { brief = "UserBrief" }
output = "PlanDraft"
model = "llm_to_engineer"
prompt = """
Return a draft of a plan that narrates the pipeline as pseudo-steps (no code):
- Explicitly indicate when you are running things in sequence,
  or in parallel (several independant steps in parallel),
  or in batch (same operation applied to N elements of a list)
  or based on a condition
- For each pipe: state the pipe's description, inputs (by name using snake_case), and the output (by name using snake_case),
DO NOT indicate the inputs or output type. Just name them.
- Be aware of the steps where you will want structured outputs or inputs. Make sense of it but be concise.

Available pipe controllers:
- PipeSequence: A pipe that executes a sequence of pipes: it needs to reference the pipes it will execute.
- PipeParallel: A pipe that executes a few pipes in parallel. It needs to reference the pipes it will execute.
  The results of each pipe will be in the working memory. The output MUST BE "Dynamic".
- PipeCondition: A pipe that based on a conditional expression, branches to a specific pipe.
  You have to explain what the expression of the condition is,
  and reference the different pipes that well be executed according to the condition.

When describing the task of a pipe controller, be concise, don't detail all the sub-pipes.

Available pipe operators:
- PipeLLM: A pipe that uses an LLM to generate a text, or a structured object. It is a vision LLM so it can also use images.
  CRITICAL: When extracting MULTIPLE items (articles, employees, products), use multiple_output = true with SINGULAR concepts!
  - Create concept "Article" (not "Articles") with fields "item_name", "quantity" (not "item_names", "quantities")
  - Then set multiple_output = true to get a list of Article objects
- PipeImgGen: A pipe that uses an AI model to generate an image.
  VERY IMPORTANT: IF YOU DECIDE TO CREATE A PipeImgGen, YOU ALSO HAVE TO CREATE A PIPELLM THAT WILL WRITE THE PROMPT, AND THAT NEEDS TO PRECEED THE PIPEIMGEN, based on the necessary elements.
  That means that in the MAIN pipeline, the prompt MUST NOT be considered as an input. It should be the output of a step that generates the prompt.
- PipeExtract: A pipe that uses an OCR technology to extract text from an image or a pdf.
  VERY IMPORTANT: THE INPUT OF THE PIPEOCR MUST BE either an image or a pdf or a concept which refines one of them.


Be smart about splitting the workflow into steps (sequence or parallel):
- You can use an LLM to extract or analyze several things at the same time, they can be output as a single concept which will be structured with attributes etc.
- But don't ask the LLM for many things which are unrelated, it would lose reliability.

Keep your style concise, no need to write tags such as "Description:", just write what you need to write.
Do not write any intro or outro, just write the plan.

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
Variables are snake_case and concepts are PascalCase.

Your job is to clarify the different concepts used in the plan.
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
- Provide a short description concise description for each concept

If the concept can be expressed as a text, image, pdf, number, or page:
- Name the concept, define it and just write "refines: Text", "refines: PDF", or "refines: Image" etc.
- No need to define its structure
Else, if you need structure for your concept, draft its structure:
- field name in snake_case
- description:
  - description: the description of the field, in natural language
  - type: the type of the field (text, integer,boolean, number, date)
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
inputs = { concept_drafts = "ConceptDrafts", brief = "UserBrief" }
output = "concept.ConceptSpec"
multiple_output = true
model = "llm_to_engineer"
system_prompt = """
You are an expert at data extraction and json formatting.
"""
prompt = """
You are on a big journey to construct a pipeline, and this is one of the steps. 
Here is the overalle mission of the user:
@brief

Your task here is to extract a list of ConceptSpec from these concept drafts:
@concept_drafts
"""

[pipe.design_pipe_signatures]
type = "PipeLLM"
description = "Write the pipe signatures for the plan."
inputs = { plan_draft = "PlanDraft", brief = "UserBrief", concept_specs = "concept.ConceptSpec" }
output = "pipe_design.PipeSignature"
multiple_output = true
model = "llm_to_engineer"
system_prompt = """
You are a Senior engineer, very well versed in creating pipelines.
You are very thorough about naming stuff, structured and rigorous in your planning.
"""
prompt = """
Your job is to structure the required PipeSignatures for defining a pipeline which has already been drafted.

@brief

@plan_draft

{% if concept_specs %}
We have already defined the concepts you can use for inputs/outputs:
@concept_specs
And of course you still have the native concepts if required: Text, Image, PDF, Number, Page.
{% else %}
You can use the native concepts for inputs/outputs as required: Text, Image, PDF, Number, Page.
{% endif %}

Define the contracts of the pipes to build:
- For each pipe: give a unique snake_case pipe_code, a type and description, specify inputs (one or more) and output (one)
- Add as much details as possible for the description.

Available pipe controllers:
- PipeSequence: A pipe that executes a sequence of pipes: it needs to reference the pipes it will execute.
- PipeParallel: A pipe that executes a few pipes in parallel. It needs to reference the pipes it will execute.
  The results of each pipe will be in the working memory. The output MUST BE "Dynamic".
- PipeCondition: A pipe that based on a conditional expression, branches to a specific pipe.
  You have to explain what the expression of the condition is,
  and reference the different pipes that well be executed according to the condition.

When describing the task of a pipe controller, be concise, don't detail all the sub-pipes.

Available pipe operators:
- PipeLLM: A pipe that uses an LLM to generate a text, or a structured object. It is a vision LLM so it can also use images.
  CRITICAL: When extracting MULTIPLE items (articles, employees, products), use multiple_output = true with SINGULAR concepts!
  - Create concept "Article" (not "Articles") with fields "item_name", "quantity" (not "item_names", "quantities")
  - Then set multiple_output = true to get a list of Article objects
- PipeImgGen: A pipe that uses an AI model to generate an image.
  VERY IMPORTANT: IF YOU DECIDE TO CREATE A PipeImgGen, YOU ALSO HAVE TO CREATE A PIPELLM THAT WILL WRITE THE PROMPT, AND THAT NEEDS TO PRECEED THE PIPEIMGEN, based on the necessary elements.
  That means that in the MAIN pipeline, the prompt MUST NOT be considered as an input. It should be the output of a step that generates the prompt.
- PipeExtract: A pipe that extracts text from an image or a pdf. PipeExtract must have a exactly one input which must be either an `Image` or a `PDF`.

Be smart about splitting the workflow into steps (sequence or parallel):
- You can use an LLM to extract or analyze several things at the same time, they can be output as a single concept which will be structured with attributes etc.
- But don't ask the LLM for many things which are unrelated, it would lose reliability.
"""

[pipe.assemble_pipelex_bundle_spec]
type = "PipeFunc"
description = "Compile the pipelex bundle spec."
inputs = { pipe_specs = "PipeSpec", concept_specs = "ConceptSpec", domain_information = "DomainInformation" }
output = "PipelexBundleSpec"
function_name = "assemble_pipelex_bundle_spec"
