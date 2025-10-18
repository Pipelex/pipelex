domain = "mascot_design_generation"
description = "Generating cute animal mascot variants for startups based on elevator pitches and brand guidelines"
main_pipe = "imagine_mascot_variants"

[concept.ElevatorPitch]
description = """
A concise business pitch that describes a startup's value proposition, target market, and key differentiators.
"""
refines = "Text"

[concept.BrandGuidelines]
description = """
Documentation that defines a brand's visual and stylistic standards, including colors, typography, tone, and design principles.
"""
refines = "Text"

[concept.MascotIdea]
description = "A conceptual description of an animal mascot character for a brand."

[concept.MascotIdea.structure]
animal_type = { type = "text", description = "The species or type of animal (e.g., \"fox\", \"penguin\", \"octopus\")", required = true }
personality_traits = { type = "text", description = "Key personality characteristics of the mascot", required = true }
symbolic_meaning = { type = "text", description = "What the animal represents or symbolizes for the brand", required = true }
visual_style_notes = { type = "text", description = "High-level visual direction for the mascot's appearance", required = false }

[concept.ImagePrompt]
description = "A detailed text description used to generate an image through an AI image generation system."
refines = "Text"

[concept.MascotVariant]
description = "A complete mascot concept with its associated image generation prompts and rendered images."

[concept.MascotVariant.structure]
mascot_idea = { type = "text", description = "The core mascot concept", required = true }
prompt_variants = { type = "text", description = "Different image generation prompts for this mascot", required = true }
generated_images = { type = "text", description = "The rendered images corresponding to each prompt variant", required = true }

[pipe.imagine_mascot_variants]
type = "PipeSequence"
description = """
Main pipeline that orchestrates the entire mascot creation process. Takes a startup's elevator pitch and brand guidelines, generates 3 distinct mascot ideas, and for each idea produces 2 prompt variants with their corresponding rendered images. This is the entry point for the complete mascot variant generation workflow.
"""
inputs = { elevator_pitch = "ElevatorPitch", brand_guidelines = "BrandGuidelines" }
output = "MascotVariant[3]"
steps = [
    { pipe = "generate_mascot_ideas", result = "mascot_ideas" },
    { pipe = "process_each_mascot_idea", result = "mascot_variants", batch_over = "mascot_ideas", batch_as = "mascot_idea" },
]

[pipe.generate_mascot_ideas]
type = "PipeLLM"
description = """
Uses an LLM to brainstorm exactly 3 distinct cute animal mascot concepts based on the startup's elevator pitch and brand guidelines. Each mascot idea includes the animal type, personality traits, symbolic meaning for the brand, and visual style notes. The LLM analyzes the startup's value proposition and brand identity to propose mascots that align with the company's mission and aesthetic.
"""
inputs = { elevator_pitch = "ElevatorPitch", brand_guidelines = "BrandGuidelines" }
output = "MascotIdea[3]"
model = { model = "claude-4.1-opus", temperature = 0.8 }
system_prompt = """
You are a creative brand strategist specializing in mascot design. Your task is to generate structured mascot concepts that align with a startup's brand identity and value proposition. Focus on creating cute, memorable animal characters that symbolically represent the brand's mission and resonate with their target audience.
"""
prompt = """
Based on the following startup information, brainstorm exactly 3 distinct cute animal mascot concepts that would effectively represent this brand.

@elevator_pitch

@brand_guidelines

Generate 3 diverse mascot ideas that each bring a unique symbolic angle to the brand. Consider animals that naturally embody qualities aligned with the startup's mission and values.
"""

[pipe.process_each_mascot_idea]
type = "PipeSequence"
description = """
Processes a single mascot idea through the complete variant generation workflow. First generates 2 different image generation prompt variants for the mascot concept, then renders an image for each prompt. This pipe is designed to be batched over multiple mascot ideas.
"""
inputs = { mascot_idea = "MascotIdea", brand_guidelines = "BrandGuidelines" }
output = "MascotVariant"
steps = [
    { pipe = "generate_prompt_variants", result = "prompts" },
    { pipe = "generate_images_for_prompts", result = "generated_images", batch_over = "prompts", batch_as = "image_prompt" },
]

[pipe.generate_prompt_variants]
type = "PipeLLM"
description = """
Uses an LLM to create exactly 2 different image generation prompts for the same mascot concept. Each prompt variant offers a different artistic interpretation or visual approach while maintaining the core mascot idea. The prompts incorporate the brand guidelines to ensure visual consistency and are optimized for AI image generation systems with detailed descriptions of style, composition, lighting, and artistic direction.
"""
inputs = { mascot_idea = "MascotIdea", brand_guidelines = "BrandGuidelines" }
output = "ImagePrompt[2]"
model = { model = "claude-4.1-opus", temperature = 0.8 }
system_prompt = """
You are an expert at crafting AI image generation prompts. You specialize in creating detailed, effective prompts that produce high-quality mascot illustrations. You will generate structured ImagePrompt objects based on the mascot concept and brand guidelines provided.
"""
prompt = """
Create exactly 2 different image generation prompts for the following mascot concept. Each prompt should offer a distinct artistic interpretation or visual approach while maintaining the core mascot idea.

@mascot_idea

@brand_guidelines

Requirements:
- Each prompt must be VERY concise yet detailed enough for AI image generation
- Focus on visual elements: style, composition, lighting, colors, mood, artistic direction
- Incorporate the brand guidelines to ensure visual consistency
- Each variant should explore a different artistic approach (e.g., different poses, angles, art styles, or moods)
- Use best practices for AI image generation prompts
- Be specific and descriptive but avoid unnecessary verbosity
"""

[pipe.generate_images_for_prompts]
type = "PipeImgGen"
description = """
Generates a single mascot image from an image generation prompt using an AI image generation model. Takes a detailed text prompt describing the mascot's appearance, style, and composition, and renders it as a visual image. This pipe is designed to be batched over multiple prompts to generate all variant images.
"""
inputs = { image_prompt = "ImagePrompt" }
output = "Image"
