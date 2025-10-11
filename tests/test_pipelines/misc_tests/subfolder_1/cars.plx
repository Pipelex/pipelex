

domain = "cars"
description = "The test domain for handling car descriptions"
system_prompt = "You are an expert at describing cars based on their brand, model, and year."

[concept]
Car = "A car reference, including its brand, model, and year"
CarDescription = "A detailed description of a car model"

[pipe]
[pipe.generate_car_description]
type = "PipeLLM"
description = "Generate a description of a car"
inputs = { car = "Car" }
output = "CarDescription"
prompt_template = """
Given the reference to a car, generate a description of the car.

@car
"""

