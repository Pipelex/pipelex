

domain = "animals"
description = "The test domain for handling animal descriptions"
system_prompt = "You are an expert at describing animals based on their species, breed, and age."

[concept]
Animal = "An animal reference, including its species, breed, and age"
AnimalDescription = "A detailed description of an animal"

[pipe]
[pipe.generate_animal_description]
type = "PipeLLM"
description = "Generate a description of an animal"
inputs = { animal = "Animal" }
output = "AnimalDescription"
prompt = """
Given the reference to an animal, generate a description of the animal.

@animal
"""

