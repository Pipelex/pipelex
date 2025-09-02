

domain = "flows"
definition = "A collection of pipes that are used to test the flow of a pipeline"

[concept]
Color = "A color"

[pipe]
[pipe.choose_colors]
type = "PipeLLM"
definition = "Choose Colors"
output = "Color"
prompt_template = """
Choose {{ _nb_output }} colors.
"""
llm = "llm_for_creative_writing"

[pipe.sequence_for_batch_test]
type = "PipeSequence"
definition = "Sequence for parallel test"
inputs = { color = "Color" }
output = "Color"
steps = [
    { pipe = "capitalize_color", result = "capitalized_color" },
    { pipe = "capitalize_last_letter", result = "capitalized_last_letter" },
]

[pipe.capitalize_color]
type = "PipeLLM"
definition = "Capitalize Colors"
inputs = { color = "Color" }
output = "Color"
prompt_template = """
Put the first letter of a word that represents a color as a capital letter.
Here is the word:

@color

Output only the word, nothing else.
"""

[pipe.capitalize_last_letter]
type = "PipeLLM"
definition = "Capitalize Last Letter"
inputs = { capitalized_color = "Color" }
output = "Color"
prompt_template = """
Put the last letter of a word that represents a color as a capital letter.
Here is the word:

@capitalized_color

Output only the word, nothing else.
"""

