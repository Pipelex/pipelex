domain = "test_integration"
description = "Simple pipes for testing PipeBatch integration"

[concept]
UppercaseText = "Text that has been transformed to uppercase"

[pipe]

[pipe.uppercase_transformer]
type = "PipeLLM"
description = "Transform text to uppercase"
inputs = { text_item = "Text" }
output = "UppercaseText"
prompt = """
Transform the following text to uppercase and add the prefix "UPPER: ":

@text_item

Just return the transformed text, nothing else.
"""

