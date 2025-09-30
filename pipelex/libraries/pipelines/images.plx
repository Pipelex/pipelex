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


[pipe.generate_photo]
type = "PipeImgGen"
definition = "Generate a photo"
inputs = { prompt = "ImgGenPrompt" }
output = "images.Photo"

