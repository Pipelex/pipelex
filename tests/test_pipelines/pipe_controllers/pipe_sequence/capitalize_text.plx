domain = "test_integration"
description = "Test pipe for capitalizing text to uppercase"

[pipe]
[pipe.capitalize_text]
type = "PipeLLM"
description = "Transform text to uppercase"
inputs = { input_text = "Text" }
output = "Text"
prompt_template = """Transform the following text to uppercase:

@input_text.text

Return only the uppercase text, nothing else."""

[pipe.add_prefix]
type = "PipeLLM"
description = "Add PROCESSED prefix to text"
inputs = { capitalized_text = "Text" }
output = "Text"
prompt_template = """Add the prefix "PROCESSED: " to the beginning of the following text:

@capitalized_text.text

Return only the prefixed text, nothing else."""

