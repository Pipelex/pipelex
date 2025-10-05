domain = "pipe_llm_vision"
description = "Test PipeLLM with vision capabilities"

[pipe.describe_image]
type = "PipeLLM"
description = "Describe what is in the image"
inputs = { image = "Image" }
output = "Text"
llm = { llm_handle = "gpt-4o-mini", temperature = 0.3, max_tokens = 200 }
prompt_template = """
Describe what you see in this image in 2-3 sentences.
$image
"""

[pipe.analyze_image_detailed]
type = "PipeLLM"
description = "Provide detailed analysis of the image"
inputs = { photo = "Image" }
output = "Text"
llm = { llm_handle = "gpt-4o-mini", temperature = 0.5, max_tokens = 300 }
system_prompt = "You are an expert image analyst. Provide detailed, accurate descriptions."
prompt_template = """
Analyze this image and describe:
1. The main subject or objects
2. The setting and environment
3. Colors and visual style
4. Any notable details or patterns

$photo
"""

