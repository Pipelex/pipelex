domain = "startup_mascot_generation"
description = """
Generating cute animal mascot concepts and visual variants for startups based on their elevator pitch and brand guidelines.
"""
main_pipe = "generate_startup_mascot_variants"

[concept.BrandElements]
description = "Structured concept capturing key brand attributes extracted from startup materials."

[concept.BrandElements.structure]
brand_name = { type = "text", description = "The name of the startup or brand", required = true }
core_values = { type = "text", description = "List of fundamental values the brand represents", required = true }
target_audience = { type = "text", description = "Description of the intended audience or customer base", required = true }
brand_personality = { type = "text", description = "Personality traits and tone of the brand", required = true }
visual_style_preferences = { type = "text", description = "Preferred visual aesthetics, colors, and design direction", required = false }
industry_context = { type = "text", description = "The industry or sector the startup operates in", required = false }

[concept.MascotConcept]
description = "Structured concept defining a mascot idea with its characteristics."

[concept.MascotConcept.structure]
animal_type = { type = "text", description = "The type of animal chosen for the mascot", required = true }
personality_traits = { type = "text", description = "Key personality characteristics of the mascot", required = true }
visual_characteristics = { type = "text", description = "Physical appearance details and distinctive features", required = true }
brand_alignment_rationale = { type = "text", description = "Explanation of how this mascot concept aligns with brand values", required = false }
name_suggestion = { type = "text", description = "Proposed name for the mascot character", required = false }

[concept.ImagePrompt]
description = "refines: Text"
refines = "Text"

[concept.MascotVariant]
description = "Structured concept combining a mascot concept with its generated images and prompts."

[concept.MascotVariant.structure]
concept = { type = "text", description = "The mascot concept this variant is based on", required = true }
prompts = { type = "text", description = "The image generation prompts used", required = true }
images = { type = "text", description = "The generated mascot images", required = true }

[pipe.generate_startup_mascot_variants]
type = "PipeSequence"
description = """
Main pipeline that orchestrates the complete mascot generation process for a startup. Takes an elevator pitch and brand guidelines as inputs, then executes a sequence of steps to analyze brand elements, generate 3 distinct mascot concepts, create 2 prompt variants for each concept, generate images from all prompts, and compile everything into structured mascot variants. This is the entry point for the entire mascot generation workflow.
"""
inputs = { elevator_pitch = "Text", brand_guidelines = "Text" }
output = "MascotVariant[]"
steps = [
    { pipe = "extract_brand_elements", result = "brand_elements" },
    { pipe = "generate_mascot_concepts", result = "mascot_concepts" },
    { pipe = "generate_prompts_for_concepts", result = "image_prompts", batch_over = "mascot_concepts", batch_as = "mascot_concept" },
    { pipe = "generate_mascot_images", result = "mascot_images", batch_over = "image_prompts", batch_as = "image_prompt" },
    { pipe = "compile_results", result = "mascot_variants" },
]

[pipe.extract_brand_elements]
type = "PipeLLM"
description = """
Analyzes the startup's elevator pitch and brand guidelines to extract and structure key brand attributes including brand name, core values, target audience, brand personality, visual style preferences, and industry context. This structured information serves as the foundation for generating aligned mascot concepts.
"""
inputs = { elevator_pitch = "Text", brand_guidelines = "Text" }
output = "BrandElements"
model = { model = "claude-4.5-sonnet", temperature = 0.3 }
system_prompt = """
You are a brand analysis expert. Your task is to carefully analyze startup materials and extract structured brand information that will be used to generate mascot concepts. Focus on identifying the core essence of the brand, its values, personality, and visual direction.
"""
prompt = """
Analyze the following startup materials and extract the key brand elements:

@elevator_pitch

@brand_guidelines

Based on these materials, identify and extract the brand's core attributes that will inform mascot design.
"""

[pipe.generate_mascot_concepts]
type = "PipeLLM"
description = """
Creates exactly 3 distinct mascot concept ideas based on the extracted brand elements. Each concept includes the animal type, personality traits, visual characteristics, brand alignment rationale, and a name suggestion. The concepts are designed to offer diverse creative directions while maintaining alignment with the brand identity.
"""
inputs = { brand_elements = "BrandElements" }
output = "MascotConcept[3]"
model = { model = "claude-4.1-opus", temperature = 0.8 }
system_prompt = """
You are a creative brand strategist and mascot designer. Your task is to generate structured mascot concepts that align with brand identity while offering diverse creative directions.
"""
prompt = """
Based on the following brand elements, create exactly 3 distinct and diverse mascot concepts.

@brand_elements

Each concept should:
- Feature a different animal type that resonates with the brand
- Have unique personality traits that reflect brand values
- Include distinctive visual characteristics
- Provide clear rationale for brand alignment
- Suggest an appropriate name

Ensure the three concepts offer varied creative directions while all maintaining strong alignment with the brand identity.
"""

[pipe.generate_prompts_for_concepts]
type = "PipeLLM"
description = """
For each mascot concept, generates exactly 2 detailed image generation prompts with different stylistic variations. Each prompt is crafted to capture the mascot's animal type, personality traits, and visual characteristics while incorporating the brand's visual style preferences. The variations explore different artistic approaches, poses, or contexts to provide creative diversity.
"""
inputs = { mascot_concept = "MascotConcept", brand_elements = "BrandElements" }
output = "ImagePrompt[2]"
model = { model = "claude-4.1-opus", temperature = 0.8 }
system_prompt = """
You are an expert at crafting image generation prompts for mascot characters. Your task is to generate exactly 2 distinct, detailed image generation prompts that will produce high-quality mascot images. Each prompt should be concise, focused, and follow best practices for image generation. You will output structured ImagePrompt objects.
"""
prompt = """
Generate exactly 2 distinct image generation prompts for a mascot based on the following:

@mascot_concept

@brand_elements

Requirements:
- Each prompt must be VERY concise and focused (ideal for image generation models)
- Capture the animal type, personality traits, and visual characteristics
- Incorporate the brand's visual style preferences
- Create 2 different stylistic variations (e.g., different poses, artistic styles, contexts, or perspectives)
- Follow best practices for image generation prompts: be specific, descriptive, and avoid ambiguity
- Focus on visual elements that can be rendered effectively
"""

[pipe.generate_mascot_images]
type = "PipeImgGen"
description = """
Generates a mascot image from the provided image generation prompt using an AI image generation model. Produces a single high-quality image that visualizes the mascot concept according to the detailed prompt specifications.
"""
inputs = { image_prompt = "ImagePrompt" }
output = "Image"
model = "high_quality_img_gen"

[pipe.compile_results]
type = "PipeLLM"
description = """
Organizes and structures all generated mascot images with their corresponding concepts and prompts into a cohesive collection of mascot variants. Each variant combines one mascot concept with its 2 prompt variations and their generated images, creating a comprehensive presentation of all mascot options for the startup to review and select from.
"""
inputs = { mascot_concepts = "MascotConcept[]", image_prompts = "ImagePrompt[]", mascot_images = "Image[]" }
output = "MascotVariant[]"
model = "claude-4.5-sonnet"
system_prompt = """
You are a data organization specialist. Your task is to structure and compile mascot generation results into a well-organized collection of MascotVariant objects.
"""
prompt = """
Organize the mascot generation results into a structured collection.

You have:
- 3 mascot concepts
- 6 image prompts (2 per concept)
- 6 generated images (1 per prompt)

@mascot_concepts

@image_prompts

Images:
$mascot_images

Create a MascotVariant for each of the 3 mascot concepts. Each variant should include:
- The mascot concept
- The 2 prompts associated with that concept
- The 2 images generated from those prompts

Ensure the correct mapping between concepts, prompts, and images based on their generation order.
"""
