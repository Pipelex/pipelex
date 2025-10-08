

domain = "tests"
description = "This library is intended for testing purposes"

[concept]
FictionCharacter = "A character in a fiction story"
ArticleAndCritic = "An article and a critique of it"
Complex = "A complex object"

[pipe.simple_llm_test_from_image]
type = "PipeLLM"
description = "Simple LLM test from image"
inputs = { image = "Image" }
output = "Text"
prompt = """
Describe the using rap lyrics, including puns and references to the image.
@image
"""

[pipe.test_no_input]
type = "PipeLLM"
description = "No Input"
output = "Text"
model = "llm_for_testing_gen_text"
prompt = """
Explain that this is a test prompt which took no input from the user.
"""

[pipe.test_no_input_that_could_be_long]
type = "PipeLLM"
description = "No Input but generates a text that could be long"
output = "Text"
model = { model = "gpt-4o-mini", temperature = 0.5, max_tokens = 1000 }
prompt = """
Tell me a short story about a red baloon.
"""

