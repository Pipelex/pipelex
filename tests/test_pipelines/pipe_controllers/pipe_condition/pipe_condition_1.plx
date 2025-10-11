domain = "test_pipe_condition"
description = "Simple test for PipeCondition functionality"

[concept]
CategoryInput = "Input with a category field"

[pipe]
[pipe.basic_condition_by_category]
type = "PipeCondition"
description = "Route based on category field"
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression_template = "{{ input_data.category }}"

[pipe.basic_condition_by_category.pipe_map]
small = "process_small"
medium = "process_medium"
large = "process_large"

[pipe.process_small]
type = "PipeLLM"
description = "Generate random text for small items"
output = "native.Text"
prompt_template = """
Output this only: "small"
"""

[pipe.process_medium]
type = "PipeLLM"
description = "Generate random text for medium items"
output = "native.Text"
prompt_template = """
Output this only: "medium"
"""

[pipe.process_large]
type = "PipeLLM"
description = "Generate random text for large items"
output = "native.Text"
prompt_template = """
Output this only: "large"
"""

