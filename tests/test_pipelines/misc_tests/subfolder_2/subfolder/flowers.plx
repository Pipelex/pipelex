domain = "flowers"
description = "A test domain related to flowers"
system_prompt = "You are an expert at describing flowers based on their species and color."

[concept]
Flower = "A flower reference, including its species and color"
FlowerDescription = "A detailed description of a flower"

[pipe]
[pipe.generate_flower_description]
type = "PipeLLM"
description = "Generate a description of a flower"
inputs = { flower = "Flower" }
output = "FlowerDescription"
prompt_template = """
Given the reference to a flower, generate a description of the flower.

@flower
"""

