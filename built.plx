domain = "builder"
definition = "Builder pipeline library"

[concept.Photo]
definition = "Input photograph to be analyzed and processed"
refines = "Image"

[concept.ImageDescription]
definition = "Detailed textual analysis of the photo's visual characteristics, composition, colors, objects, and overall aesthetic"
refines = "Text"

[pipe.photo_opposite_rendering_sequence]
type = "PipeSequence"
definition = "Main pipeline that orchestrates the complete photo opposite rendering process by sequentially analyzing the input photo, generating an opposite prompt, and creating the final opposite image"
inputs = { photo = { concept = "Photo" } }
output = "Image"
steps = [
    { pipe = "analyze_photo_llm", result = "image_description" },
    { pipe = "generate_opposite_prompt_llm", result = "opposite_prompt" },
    { pipe = "generate_opposite_image", result = "opposite_image" },
]

[pipe.analyze_photo_llm]
type = "PipeLLM"
definition = "Vision LLM pipe that analyzes the input photo to understand its visual characteristics, composition, colors, objects, mood, lighting, style, and overall aesthetic elements for comprehensive understanding"
inputs = { photo = { concept = "Photo" } }
output = "ImageDescription"
multiple_output = false
prompt_template = "Analyze this photo in detail. Describe all visual elements including: colors (dominant and accent colors), lighting (bright/dark, natural/artificial), mood (happy/sad, energetic/calm), composition (centered/off-center, symmetrical/asymmetrical), objects and subjects present, background elements, style (realistic/artistic, modern/vintage), textures, and overall aesthetic. Be very specific and detailed in your description as this will be used to create an opposite version. Photo: $photo"

[pipe.generate_opposite_prompt_llm]
type = "PipeLLM"
definition = "LLM pipe that takes the detailed image description and generates a comprehensive prompt for creating the opposite version by inverting colors, mood, composition, lighting, objects, and aesthetic characteristics"
inputs = { image_description = { concept = "ImageDescription" } }
output = "Text"
multiple_output = false
prompt_template = "Based on this detailed image description, create a prompt for generating the opposite version of the photo. Invert all characteristics: if colors are bright make them dark, if mood is happy make it sad, if lighting is natural make it artificial, if composition is centered make it off-center, if objects are modern make them vintage, if style is realistic make it artistic, etc. Create a detailed image generation prompt that captures all these opposite characteristics. Image description: $image_description"

[pipe.generate_opposite_image]
type = "PipeImgGen"
definition = "Image generation pipe that creates the final opposite image based on the crafted prompt, producing a visual representation that contrasts with the original photo in colors, mood, composition, and overall aesthetic"
inputs = { opposite_prompt = { concept = "Text" } }
output = "Image"
nb_output = 1
