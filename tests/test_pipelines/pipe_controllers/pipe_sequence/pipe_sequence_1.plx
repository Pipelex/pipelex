domain = "simple_text_processing"
description = "Simple text processing pipeline without batching"
system_prompt = "You are an expert at text analysis and processing"

[concept]
RawText = "Raw input text to be processed"
CleanedText = "Text that has been cleaned and normalized"
SummaryText = "A summary of the processed text"

[pipe]
[pipe.simple_text_sequence]
type = "PipeSequence"
description = "Process text through cleaning and summarization"
inputs = { raw_text = "RawText" }
output = "SummaryText"
steps = [
    { pipe = "clean_text", result = "cleaned_text" },
    { pipe = "generate_summary", result = "final_summary" },
]

[pipe.clean_text]
type = "PipeLLM"
description = "Clean and normalize the input text"
inputs = { raw_text = "RawText" }
output = "CleanedText"
llm = "llm_for_testing_gen_text"
prompt_template = """
Clean and normalize the following text by:
- Removing extra whitespace
- Fixing basic grammar and punctuation
- Standardizing formatting

@raw_text
"""

[pipe.generate_summary]
type = "PipeLLM"
description = "Generate a summary of the cleaned text"
inputs = { cleaned_text = "CleanedText" }
output = "SummaryText"
llm = "llm_for_testing_gen_text"
prompt_template = """
Generate a concise summary of the following text in 2-3 sentences:

@cleaned_text
"""

