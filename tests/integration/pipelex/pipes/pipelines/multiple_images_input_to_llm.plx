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
Create a mascot presentation for a startup based on the following information:

And here are the corresponding mascot images:
$collection_of_images

Compile a comprehensive yet concise presentation that:
1. Briefly introduces the brand context
2. Presents each mascot option with its concept details and visual representation
3. Highlights the rationale for each mascot's brand fit
4. Provides a clear summary to help stakeholders make a decision

Keep the presentation focused and professional.
"""
