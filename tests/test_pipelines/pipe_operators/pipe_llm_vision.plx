domain = "pipe_llm_vision"
description = "Test PipeLLM with vision capabilities"

[concept]
VisionAnalysis = "Some analysis based on the image"
BasicDescription = "Basic description of the image"

[concept.Photo]
description = "A photo"
refines = "Image"

[pipe.describe_image]
type = "PipeLLM"
description = "Describe what is in the image"
inputs = { image = "Image" }
output = "Text"
model = "llm_for_testing_vision"
prompt = """
Describe what you see in this image in 1-2 sentences, be concise.
$image
"""

[pipe.describe_image_number_1_only]
type = "PipeLLM"
description = "Describe what is in the image"
inputs = { image_a = "Image", image_b = "Image" }
output = "BasicDescription"
model = "llm_for_diagram_to_text"
prompt = """
Describe what you see in $image_a only.
Completely ignore $image_b.
"""

[pipe.describe_image_number_2_only]
type = "PipeLLM"
description = "Describe what is in the image"
inputs = { image_a = "Image", image_b = "Image" }
output = "BasicDescription"
model = "llm_for_diagram_to_text"
prompt = """
Describe what you see in $image_b only.
Completely ignore $image_a.
"""


[pipe.vision_analysis]
type = "PipeLLM"
description = "Provide detailed analysis of the image"
inputs = { image = "Photo" }
output = "VisionAnalysis"
model = "llm_for_diagram_to_text"
system_prompt = "You are an expert image analyst. Provide detailed, accurate descriptions."
prompt = """
Analyze this image and describe what's the main topic etc.
$image
--------------------------------
"""

