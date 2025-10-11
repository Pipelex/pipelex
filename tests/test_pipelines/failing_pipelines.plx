

domain = "failing_pipelines"

[pipe]
[pipe.dummy]
type = "PipeLLM"
description = "This pipe is a dummy pipe"
output = "Text"
llm = { llm_handle = "gpt-4o-mini", temperature = 1, max_tokens = 50 }
prompt_template = """
Output only "Hello".
"""

[pipe.infinite_loop_1]
type = "PipeSequence"
description = "This pipe will cause an infinite loop"
output = "Text"
steps = [
    { pipe = "dummy", result = "dummy_result" },
    { pipe = "infinite_loop_1", result = "disaster" },
]

