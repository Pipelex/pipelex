domain = "test_simple"
definition = "A pipeline for testing simple pipes"


[pipe]
[pipe.write_haiku]
type = "PipeLLM"
definition = "Write a haiku about pipes"
output = "Text"
prompt_template = """
Write a haiku about pipes.
"""
# llm = "llm_for_testing_gen_text"
llm = "gpt-4o"
# llm = { llm_handle = "gpt-4o", temperature = 1.1, max_tokens = "auto" }
# llm = { llm_handle = "gemini-2.5-pro", temperature = 1, max_tokens = "auto" }

