domain = "test_integration"
description = "Test pipes for PipeCondition based on text length"

[pipe]

[pipe.capitalize_long_text]
type = "PipeLLM"
description = "Capitalize text for long inputs"
inputs = { input_text = "Text" }
output = "Text"
prompt_template = """Transform the following LONG text to uppercase and add "LONG: " prefix:

@input_text.text

Return only the prefixed uppercase text, nothing else."""

[pipe.add_prefix_short_text]
type = "PipeLLM"
description = "Add prefix for short text inputs"
inputs = { input_text = "Text" }
output = "Text"
prompt_template = """Add the prefix "SHORT: " to the beginning of the following text:

@input_text.text

Return only the prefixed text, nothing else."""

