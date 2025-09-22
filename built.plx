domain = "builder"
definition = "Builder pipeline library"

[concept.PhotoAnalysis]
definition = "Structured analysis of a photo's visual elements, objects, colors, mood, and composition"

[concept.PhotoAnalysis.structure]
main_object = { type = "text", definition = "The primary object or subject visible in the photo", required = true }
color_scheme = { type = "text", definition = "The dominant color palette of the photo", required = true }
lighting = { type = "text", definition = "The lighting conditions in the photo (bright, dim, natural, artificial, etc.)", required = true }
mood = { type = "text", definition = "The emotional tone or atmosphere conveyed by the photo", required = true }
composition = { type = "text", definition = "The arrangement and positioning of elements within the photo", required = true }

[concept.OppositeMapping]
definition = "Mapping of original photo elements to their conceptual opposites"

[concept.OppositeMapping.structure]
opposite_object = { type = "text", definition = "The conceptual opposite of the main object in the original photo", required = true }
opposite_color = { type = "text", definition = "The opposite color scheme to the original photo's palette", required = true }
opposite_lighting = { type = "text", definition = "The opposite lighting condition to the original photo", required = true }
opposite_mood = { type = "text", definition = "The opposite emotional tone or atmosphere to the original photo", required = true }
opposite_composition = { type = "text", definition = "The opposite arrangement or positioning style to the original photo", required = true }

[pipe.photo_to_opposite_pipeline]
type = "PipeSequence"
definition = "Main pipeline that takes a photo and generates its conceptual opposite through sequential analysis and generation steps"
inputs = { ocr_input = { concept = "Image" }, prompt = { concept = "ImgGenPrompt" } }
output = "OppositeImage"
steps = [
    { pipe = "extract_photo_content", result = "extracted_content" },
    { pipe = "analyze_photo_elements", result = "photo_analysis" },
    { pipe = "determine_opposites", result = "opposite_concepts" },
    { pipe = "create_opposite_prompt", result = "image_prompt" },
    { pipe = "generate_opposite_image", result = "opposite_image" },
]

[pipe.extract_photo_content]
type = "PipeOcr"
definition = "Extracts and analyzes the visual content of the input photo to understand what objects, scenes, and elements are present"
inputs = { ocr_input = { concept = "Image" } }
output = "String"
ocr = "mistral-ocr"

[pipe.analyze_photo_elements]
type = "PipeLLM"
definition = "Analyzes the extracted photo content to identify and categorize key visual elements including objects, colors, lighting, mood, and composition"
inputs = { extracted_content = { concept = "String" } }
output = "PhotoAnalysis"
multiple_output = false
prompt_template = "Analyze this photo description and identify the key elements: @extracted_content\n\nProvide a structured analysis including:\n- Main objects and subjects\n- Color scheme and palette\n- Lighting conditions (bright/dark, natural/artificial)\n- Overall mood and atmosphere\n- Composition and style\n- Setting and environment"

[pipe.determine_opposites]
type = "PipeLLM"
definition = "Determines the conceptual opposites for each analyzed element, creating mappings from original characteristics to their antithetical counterparts"
inputs = { photo_analysis = { concept = "PhotoAnalysis" } }
output = "OppositeMapping"
multiple_output = false
prompt_template = "Based on this photo analysis: @photo_analysis\n\nDetermine the conceptual opposites for each element:\n- If objects are organic, make them mechanical; if indoor, make outdoor\n- Invert color schemes (warm to cool, bright to dark)\n- Reverse lighting (day to night, bright to dim)\n- Flip mood (happy to sad, calm to chaotic)\n- Change composition (crowded to empty, symmetrical to asymmetrical)\n\nProvide clear opposite mappings for each category."

[pipe.create_opposite_prompt]
type = "PipeLLM"
definition = "Creates a detailed and comprehensive image generation prompt that describes the opposite scene based on the determined opposite mappings"
inputs = { opposite_concepts = { concept = "OppositeMapping" } }
output = "String"
multiple_output = false
prompt_template = "Create a detailed image generation prompt based on these opposite concepts: @opposite_concepts\n\nWrite a vivid, specific prompt that describes:\n- The opposite objects and subjects in detail\n- The inverted color palette and lighting\n- The contrasting mood and atmosphere\n- The reversed composition and setting\n\nMake it detailed enough for high-quality image generation, including artistic style, camera angle, and visual quality descriptors."

[pipe.generate_opposite_image]
type = "PipeImgGen"
definition = "Generates the final opposite image using the detailed prompt created from the opposite concept analysis"
inputs = { prompt = { concept = "ImgGenPrompt" } }
output = "OppositeImage"
nb_output = 1
