domain = "test_integration"
description = "Simple pipes for testing PipeBatch integration"

[concept]
UppercaseText = "Text that has been transformed to uppercase"
TextList = "List of Text"

[pipe]
[pipe.test_pipe_batch]
type = "PipeBatch"
description = "Test pipe batch"
inputs = { text_item = "Text", text_list = "TextList" }
output = "UppercaseText"
branch_pipe_code = "uppercase_transformer"
input_list_name = "text_list"
input_item_name = "text_item"

[pipe.uppercase_transformer]
type = "PipeLLM"
description = "Transform text to uppercase"
inputs = { text_item = "Text" }
output = "UppercaseText"
prompt_template = """
Transform the following text to uppercase and add the prefix "UPPER: ":

@text_item

Just return the transformed text, nothing else.
"""

