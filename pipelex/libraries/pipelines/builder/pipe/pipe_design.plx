domain = "pipe_design"
definition = "Build and process pipes."

[concept]
PipeSignature = "A pipe contract which says what the pipe does, not how it does it: code (the pipe code in snake_case), type, description, inputs, output."
PipeSpec = "A structured spec for a pipe (union)."
# Pipe controllers
PipeBatchSpec = "A structured spec for a pipe batch."
PipeConditionSpec = "A structured spec for a pipe condition."
PipeParallelSpec = "A structured spec for a pipe parallel."
PipeSequenceSpec = "A structured spec for a pipe sequence."
# Pipe operators
PipeFuncSpec = "A structured spec for a pipe func."
PipeImgGenSpec = "A structured spec for a pipe img gen."
# PipeComposeSpec = "A structured spec for a pipe jinja2."
PipeLLMSpec = "A structured spec for a pipe llm."
PipeOcrSpec = "A structured spec for a pipe ocr."
PipeFailure = "Details of a single pipe failure during dry run."

[pipe]

[pipe.detail_pipe_spec]
type = "PipeCondition"
definition = "Route by signature.type to the correct spec emitter."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "ConceptSpec" }
output = "Dynamic"
expression = "pipe_signature.type"

[pipe.detail_pipe_spec.pipe_map]
PipeSequence  = "detail_pipe_sequence"
PipeParallel  = "detail_pipe_parallel"
PipeCondition = "detail_pipe_condition"
PipeLLM       = "detail_pipe_llm"
PipeOcr       = "detail_pipe_ocr"
PipeImgGen    = "detail_pipe_img_gen"
# PipeCompose   = "detail_pipe_compose"

# ────────────────────────────────────────────────────────────────────────────────
# PIPE CONTROLLERS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_sequence]
type = "PipeLLM"
definition = "Build a PipeSequenceSpec from the signature (children referenced by code)."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeSequenceSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeSequenceSpec to orchestrate a sequence of pipe steps that will run one after the other.

This PipeSequence is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeSequence related to this signature:
@pipe_signature
"""

[pipe.detail_pipe_parallel]
type = "PipeLLM"
definition = "Build a PipeParallelSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeParallelSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeParallelSpec to orchestrate a bunch of pipe steps that will run in parallel.

This PipeParallel is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeParallel related to this signature:
@pipe_signature
"""

[pipe.detail_pipe_condition]
type = "PipeLLM"
definition = "Build a PipeConditionSpec from the signature (provide expression/pipe_map consistent with children)."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeConditionSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeConditionSpec to route to the correct pipe step based on a conditional expression.

This PipeCondition is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeCondition related to this signature:
@pipe_signature
"""

# ────────────────────────────────────────────────────────────────────────────────
# PIPE OPERATORS
# ────────────────────────────────────────────────────────────────────────────────

[pipe.detail_pipe_llm]
type = "PipeLLM"
definition = "Build a PipeLLMSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeLLMSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeLLMSpec to use an LLM to generate a text, or a structured object using different kinds of inputs.
Whatever it's really going to do has already been decided, as you can see:

This PipeLLM is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeLLM related to this signature:
@pipe_signature

If it's a structured generation, indicate it in the system_prompt to clarify the task.
If it's to generate free form text, the prompt_template should indicate to be concise.
If it's to generate an image generation, the prompt_template should indicate to be VERY concise and focus and apply the best practice for image generation.
"""

[pipe.detail_pipe_ocr]
type = "PipeLLM"
definition = "Build a PipeOcrSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeOcrSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeOcrSpec to extract text from an image or a pdf.

This PipeOcr is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeOcr related to this signature:
@pipe_signature
"""

[pipe.detail_pipe_img_gen]
type = "PipeLLM"
definition = "Build a PipeImgGenSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeImgGenSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeImgGenSpec to generate an image from a text prompt.

This PipeImgGen is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeImgGen related to this signature:
@pipe_signature

The inputs for the image has to be a single input which must be a Text or another concept which refines Text.
"""

[pipe.detail_pipe_compose]
type = "PipeLLM"
definition = "Build a PipeComposeSpec from the signature."
inputs = { plan_draft = "PlanDraft", pipe_signature = "PipeSignature", concept_specs = "concept.ConceptSpec" }
output = "PipeComposeSpec"
llm = "llm_to_engineer"
prompt_template = """
Your job is to design a PipeComposeSpec to render a jinja2 template.

This PipeCompose is part of a larger pipeline:
@plan_draft

You will specifically generate the PipeCompose related to this signature:
@pipe_signature

You can ONLY USE THE INPUTS IN THIS PIPE SIGNATURE.

Here are the Jinja2 filters that are supported:
abs — Returns the absolute value of a number.
attr — Gets an attribute from an object, returning undefined if missing.
batch — Groups items into sublists of a given size, optionally filling blanks.
capitalize — Uppercases the first character and lowercases the rest.
center — Centers a string within a given width.
default — Returns a fallback value if the input is undefined (or falsey if enabled).
dictsort — Sorts a dict and yields (key, value) pairs by key or value.
escape — HTML-escapes &, <, >, ' and ".
filesizeformat — Formats bytes as human-readable sizes (kB/MB or KiB/MiB).
first — Returns the first item of a sequence.
float — Converts a value to float with an optional default.
forceescape — Forces HTML escaping even if marked safe.
format — Applies printf-style string formatting.
groupby — Groups items by an attribute (sorted first).
indent — Indents each line of a string by a given width.
int — Converts a value to int with base and default support.
items — Iterates over a mapping’s items, empty if undefined.
join — Concatenates sequence items with an optional separator or attribute.
last — Returns the last item of a sequence.
length — Returns the number of items (alias: count).
list — Converts the value to a list (strings become lists of characters).
lower — Converts a string to lowercase.
map — Extracts an attribute or applies a filter across a sequence.
max — Returns the largest item, optionally by attribute.
min — Returns the smallest item, optionally by attribute.
pprint — Pretty-prints a value for debugging.
random — Returns a random item from a sequence.
reject — Filters out items where a test passes.
rejectattr — Filters out items based on an attribute test.
replace — Replaces occurrences of a substring with another.
reverse — Reverses a string or iterable.
round — Rounds a number with precision and method (common/ceil/floor).
safe — Marks a string as safe and prevents auto-escaping.
select — Keeps only items where a test passes.
selectattr — Keeps only items whose attribute passes a test.
slice — Slices items into N columns (lists of lists), with optional fill.
sort — Sorts an iterable, with reverse, case, and attribute options.
string — Converts to string while preserving Markup safety.
striptags — Removes HTML/XML tags and collapses whitespace.
sum — Sums numbers or an attribute across items, with a start value.
title — Title-cases the string (each word capitalized).
tojson — Serializes a value to JSON and marks it safe for HTML.
trim — Strips leading and trailing characters (default: whitespace).
truncate — Shortens text to a length with optional word-safe ellipsis.
unique — Yields unique items in first-seen order, optional attribute.
upper — Converts a string to uppercase.
urlencode — URL-encodes a string or builds a query string from pairs.
urlize — Converts URLs/emails in text into clickable links.
wordcount — Counts words in a string.
wordwrap — Wraps text to a given width with options for breaks.
xmlattr — Builds safe HTML/XML attributes from a dict.
"""

# ────────────────────────────────────────────────────────────────────────────────
# PIPE FIXERS — one per pipe type, all fixing specific pipe type issues
# ────────────────────────────────────────────────────────────────────────────────

# [pipe.fix_failing_pipe]
# type = "PipeCondition"
# definition = "Route to specific pipe fixer based on the failing pipe type."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "Dynamic"
# expression = "pipe_failure.pipe.type"

# [pipe.fix_failing_pipe.pipe_map]
# PipeLLM = "fix_failing_llm_pipe"
# PipeImgGen = "fix_failing_imggen_pipe"
# PipeOcr = "fix_failing_ocr_pipe"
# PipeFunc = "fix_failing_func_pipe"
# PipeCompose = "fix_failing_jinja2_pipe"
# PipeSequence = "fix_failing_sequence_pipe"
# PipeParallel = "fix_failing_parallel_pipe"
# PipeCondition = "fix_failing_condition_pipe"
# PipeBatch = "fix_failing_batch_pipe"

# [pipe.fix_failing_llm_pipe]
# type = "PipeLLM"
# definition = "Fix a failing PipeLLM spec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "PipeLLMSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing PipeLLM spec.

# Failing pipe:
# @pipe_failure.pipe_spec

# Error message:
# @pipe_failure.error_message

# Please provide only the corrected PipeLLMSpec. Common LLM pipe issues to fix:
# - Missing input variables in the pipe inputs that are referenced in prompt_template
# - Incorrect variable names in prompt templates (use $ for inline, @ for blocks)
# - Wrong concept types for inputs/outputs
# - Missing llm configuration
# - Invalid prompt template syntax
# """

# [pipe.fix_failing_imggen_pipe]
# type = "PipeLLM"
# definition = "Fix a failing PipeImgGen spec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "PipeImgGenSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing PipeImgGen spec.

# Failing pipe:
# @pipe_failure.pipe_spec

# Error message:
# @pipe_failure.error_message

# Please provide only the corrected PipeImgGenSpec. Common ImgGen pipe issues to fix:
# - Missing or incorrect prompt input (should be text concept)
# - Invalid img_gen
# - Missing required inputs for dynamic prompt generation
# """

# [pipe.fix_failing_ocr_pipe]
# type = "PipeLLM"
# definition = "Fix a failing PipeOcr spec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "PipeOcrSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing PipeOcr spec.

# VERY IMPORTANT: THE INPUT OF THE PIPEOCR must be either an image or a pdf or a concept which refines one of them.
# Failing pipe:
# @pipe_failure.pipe_spec

# Error message:
# @pipe_failure.error_message

# Please provide only the corrected PipeOcrSpec. Common OCR pipe issues to fix:
# - Input must be of type Image or PDF
# - Output should typically be Page (native concept)
# - Missing or incorrect input concept types
# """

# [pipe.fix_failing_func_pipe]
# type = "PipeLLM"
# definition = "Fix a failing PipeFunc spec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "PipeFuncSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing PipeFunc spec.

# Failing pipe:
# @pipe_failure.pipe_spec

# Error message:
# @pipe_failure.error_message

# Please provide only the corrected PipeFuncSpec. Common Func pipe issues to fix:
# - Missing or incorrect function_name
# - Wrong input/output concept types for the function
# - Function not available in registry
# """

# [pipe.fix_failing_jinja2_pipe]
# type = "PipeLLM"
# definition = "Fix a failing PipeCompose spec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "PipeComposeSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing PipeCompose spec.

# Failing pipe:
# @pipe_failure.pipe_spec

# Error message:
# @pipe_failure.error_message

# Please provide only the corrected PipeComposeSpec. Common Jinja2 pipe issues to fix:
# - Invalid Jinja2 template syntax
# - Missing input variables referenced in template
# - Wrong concept types for inputs/outputs
# """

# [pipe.fix_failing_sequence_pipe]
# type = "PipeLLM"
# definition = "Fix a failing PipeSequence spec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "PipeSequenceSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing PipeSequence spec.

# Failing pipe:
# @pipe_failure.pipe_spec

# Error message:
# @pipe_failure.error_message

# Please provide only the corrected PipeSequenceSpec. Common Sequence pipe issues to fix:
# - Missing input variables needed by sub-pipes in steps
# - Referenced pipe codes in steps that don't exist
# - Circular dependencies in step order
# - Wrong result names in steps
# """

# [pipe.fix_failing_parallel_pipe]
# type = "PipeLLM"
# definition = "Fix a failing PipeParallel spec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "PipeParallelSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing PipeParallel spec.

# Failing pipe:
# @pipe_failure.pipe_spec

# Error message:
# @pipe_failure.error_message

# Please provide only the corrected PipeParallelSpec. Common Parallel pipe issues to fix:
# - Missing input variables needed by parallel sub-pipes
# - Referenced pipe codes that don't exist
# - Incompatible output types from parallel branches
# """

# [pipe.fix_failing_condition_pipe]
# type = "PipeLLM"
# definition = "Fix a failing PipeCondition spec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "PipeConditionSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing PipeCondition spec.

# Failing pipe:
# @pipe_failure.pipe_spec

# Error message:
# @pipe_failure.error_message

# Please provide only the corrected PipeConditionSpec. Common Condition pipe issues to fix:
# - Invalid expression or expression_template syntax
# - Referenced pipe codes in pipe_map that don't exist
# - Missing input variables referenced in expression
# - Incompatible output types from different condition branches
# """

# [pipe.fix_failing_batch_pipe]
# type = "PipeLLM"
# definition = "Fix a failing PipeBatch spec based on its specific error."
# inputs = { pipelex_bundle_spec = "PipelexBundleSpec", pipe_failure = "PipeFailure" }
# output = "PipeBatchSpec"
# llm = "llm_to_engineer"
# prompt_template = """
# Fix this failing PipeBatch spec.

# Failing pipe:
# @pipe_failure.pipe_spec

# Error message:
# @pipe_failure.error_message

# Please provide only the corrected PipeBatchSpec. Common Batch pipe issues to fix:
# - Missing branch_pipe_code or referenced pipe that doesn't exist
# - Wrong input types for batch processing (should be ListContent)
# - Missing batch parameters configuration
# """

