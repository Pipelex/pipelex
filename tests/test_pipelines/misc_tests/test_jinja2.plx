domain = "test_jinja2"
description = "This library is intended for testing Jinja2"

[pipe.jinja2_test_1]
type = "PipeCompose"
description = "Jinja2 test 1"
inputs = { text = "Text" }
output = "Text"
jinja2 = """
This is a simple test prompt:
@text
"""
prompting_style = { tag_style = "square_brackets", text_format = "markdown" }
template_category = "llm_prompt"

