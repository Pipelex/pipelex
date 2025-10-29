domain = "startup_mascot_design"
description = """
Generating cute animal mascot concepts with style variants and rendered images for startups based on elevator pitches and brand guidelines
"""
main_pipe = "generate_mascot_portfolio"

[concept.ElevatorPitch]
description = """
A concise business pitch that explains what a startup does, its value proposition, and target market.
"""
refines = "Text"

[concept.BrandGuideline]
description = """
Documentation that defines a brand's visual and communication standards, including colors, typography, tone, and design principles.
"""
refines = "Text"

[concept.MascotConcept]
description = "A proposed mascot idea for a brand."

[concept.MascotConcept.structure]
animal_type = { type = "text", description = "The species or type of animal chosen for the mascot", required = true }
personality_traits = { type = "text", description = "Character attributes and behavioral qualities of the mascot", required = true }
symbolic_meaning = { type = "text", description = "What the mascot represents or symbolizes for the brand", required = true }
visual_characteristics = { type = "text", description = "Physical appearance details and distinctive features", required = true }

[concept.StyleVariant]
description = "An artistic style interpretation for visual content."

[concept.StyleVariant.structure]
style_name = { type = "text", description = "The name or label of the artistic style", required = true }
style_description = { type = "text", description = "Explanation of the artistic style characteristics", required = true }
visual_approach = { type = "text", description = "How the style will be applied visually", required = true }

[concept.ImagePrompt]
description = "A detailed text prompt used to generate an image through an AI image generation system."
refines = "Text"

[pipe.generate_mascot_portfolio]
type = "PipeSequence"
description = """
Main pipeline that generates a complete portfolio of mascot concepts with style variants and rendered images for a startup based on its elevator pitch and brand guidelines
"""
inputs = { elevator_pitch = "ElevatorPitch", brand_guidelines = "BrandGuideline" }
output = "Image[]"
steps = [
    { pipe = "generate_mascot_concepts", result = "mascot_concepts" },
    { pipe = "develop_concepts_with_variants", result = "mascot_portfolio" },
]

[pipe.generate_mascot_concepts]
type = "PipeLLM"
description = "Analyzes the startup's elevator pitch and brand guidelines to generate 2 distinct mascot concepts"
inputs = { elevator_pitch = "ElevatorPitch", brand_guidelines = "BrandGuideline" }
output = "MascotConcept[2]"
model = "llm_for_creative_writing"
system_prompt = """
You are a creative brand strategist specializing in mascot design. Your task is to generate structured mascot concepts that align with a startup's brand identity and positioning.
"""
prompt = """
Based on the startup's elevator pitch and brand guidelines provided below, generate 2 distinct mascot concepts that would effectively represent the brand.

@elevator_pitch

@brand_guidelines

Create 2 unique mascot concepts that capture different aspects of the brand's identity and appeal to the target audience.
"""

[pipe.develop_concepts_with_variants]
type = "PipeBatch"
description = "For each mascot concept, generates 3 style variants and renders images for each variant"
inputs = { mascot_concepts = "MascotConcept[]", brand_guidelines = "BrandGuideline" }
output = "Image[]"
branch_pipe_code = "develop_single_concept"
input_list_name = "mascot_concepts"
input_item_name = "mascot_concept"

[pipe.develop_single_concept]
type = "PipeSequence"
description = "Develops a single mascot concept through style variants to final rendered images"
inputs = { mascot_concept = "MascotConcept", brand_guidelines = "BrandGuideline" }
output = "Image[]"
steps = [
    { pipe = "generate_style_variants", result = "style_variants" },
    { pipe = "render_style_variants", result = "concept_images" },
]

[pipe.generate_style_variants]
type = "PipeLLM"
description = "Creates 3 different artistic style interpretations for a specific mascot concept"
inputs = { mascot_concept = "MascotConcept", brand_guidelines = "BrandGuideline" }
output = "StyleVariant[3]"
model = "llm_for_visual_design"
system_prompt = """
You are a creative visual designer specializing in brand mascot development. Your task is to generate structured StyleVariant concepts that explore different artistic interpretations.
"""
prompt = """
Based on the following mascot concept and brand guidelines, create exactly 3 distinct artistic style variants that could be used to visualize this mascot.

@mascot_concept

@brand_guidelines

Generate 3 diverse artistic style interpretations that would work well for this mascot while respecting the brand guidelines. Consider different visual approaches such as minimalist, detailed illustration, geometric, playful cartoon, sophisticated vector art, hand-drawn, 3D rendered, etc.
"""

[pipe.render_style_variants]
type = "PipeBatch"
description = "Renders each style variant as an actual image"
inputs = { style_variants = "StyleVariant[]", mascot_concept = "MascotConcept", brand_guidelines = "BrandGuideline" }
output = "Image[]"
branch_pipe_code = "render_single_variant"
input_list_name = "style_variants"
input_item_name = "style_variant"

[pipe.render_single_variant]
type = "PipeSequence"
description = "Converts a single style variant into a rendered mascot image"
inputs = { mascot_concept = "MascotConcept", style_variant = "StyleVariant", brand_guidelines = "BrandGuideline" }
output = "Image"
steps = [
    { pipe = "write_image_prompt", result = "image_prompt" },
    { pipe = "generate_mascot_image", result = "final_image" },
]

[pipe.write_image_prompt]
type = "PipeLLM"
description = """
Crafts a detailed image generation prompt combining mascot characteristics, style variant, and brand guidelines
"""
inputs = { mascot_concept = "MascotConcept", style_variant = "StyleVariant", brand_guidelines = "BrandGuideline" }
output = "ImagePrompt"
model = "llm_for_creative_writing"
system_prompt = """
You are an expert at writing image generation prompts. Your task is to create a concise, focused prompt that will generate a high-quality mascot image. Apply best practices for image generation: be specific about visual details, use clear descriptive language, and focus on the most important visual elements.
"""
prompt = """
Create a detailed image generation prompt for a mascot based on the following information:

@mascot_concept

@style_variant

@brand_guidelines

Write a VERY concise and focused image generation prompt that combines the mascot's characteristics with the artistic style while respecting the brand guidelines. Focus on the most important visual elements.
"""

[pipe.generate_mascot_image]
type = "PipeImgGen"
description = "Renders the final mascot visualization using AI image generation"
inputs = { image_prompt = "ImagePrompt" }
output = "Image"
model = "gen_image_high_quality"
