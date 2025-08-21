domain = "images"
definition = "Generic image-related domain"

[concept]
VisualDescription = "Visual description of something"

[concept.ImgGenPrompt]
definition = "Prompt to generate an image"
refines = "Text"

[concept.Photo]
definition = "Photo"
refines = "Image"

[pipe]

#################################################################
# Vision: PipeLLM taking images as input
#################################################################

[pipe.describe_image]
type = "PipeLLM"
definition = "Describe an image"
inputs = { image = "Image" }
output = "VisualDescription"
system_prompt = "You are a very good observer."
llm = "llm_to_describe_img"
prompt_template = """
Describe the provided image in great detail.
"""

[pipe.describe_photo]
type = "PipeLLM"
definition = "Describe a photo"
inputs = { photo = "Photo" }
output = "VisualDescription"
system_prompt = "You are a very good observer."
llm = "llm_to_describe_img"
prompt_template = """
Describe the provided photo and how it was shot: scene, lighting, camera, etc.
"""

#################################################################
# Image generation: PipeImgGen generating images as output
#################################################################


# PipeImgGen requires to have a single input
# It can be named however you want,
# but it must be either an ImgGenPrompt or a concept which refines ImgGenPrompt
[pipe.generate_image]
type = "PipeImgGen"
definition = "Generate an image"
inputs = { prompt = "ImgGenPrompt" }
output = "Image"
nb_steps = 2


[pipe.generate_photo]
type = "PipeImgGen"
definition = "Generate a photo"
inputs = { prompt = "ImgGenPrompt" }
output = "images.Photo"
nb_steps = 8

