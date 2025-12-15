domain = "test_multiple_images_input_to_llm"
description = "Test pipeline that takes multiple images as input to a PipeLLM."

[concept]
Analysis = "An analysis of the collection ofimages."

[pipe.analyze_image_collection]
type = "PipeLLM"
description = """
Analyze the collection of images: their common features, differences, and any other relevant information.
"""
inputs = { collection_of_images = "Image[]" }
output = "Analysis"
model = "llm_for_creative_writing"
prompt = """
Analyze this collection of images: their common features, differences, and any other relevant information.

$collection_of_images
"""
