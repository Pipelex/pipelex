domain = "test_pipe_condition_2"
description = "Simple test for PipeCondition functionality using expression"

[concept]
CategoryInput = "Input with a category field"

[pipe]
[pipe.basic_condition_by_category_2]
type = "PipeCondition"
description = "Route based on category field using expression"
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression = "input_data.category"
default_outcome = "continue"

[pipe.basic_condition_by_category_2.outcomes]
small = "process_small_2"
medium = "process_medium_2"
large = "process_large_2"

[pipe.process_small_2]
type = "PipeLLM"
description = "Generate random text for small items"
output = "native.Text"
prompt = """
Output this only: "small"
"""

[pipe.process_medium_2]
type = "PipeLLM"
description = "Generate random text for medium items"
output = "native.Text"
prompt = """
Output this only: "medium"
"""

[pipe.process_large_2]
type = "PipeLLM"
description = "Generate random text for large items"
output = "native.Text"
prompt = """
Output this only: "large"
"""

