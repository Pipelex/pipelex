

domain = "test_multiplicity"
description = "Test library about multiplicity"

[concept]
Color = "A color"
ProductOfNature = "Something produced by Nature"
FantasyScene = "A fantasy scene"

[pipe.original_power_ranger_colors]
type = "PipeLLM"
description = "Recall the colors of the original power rangers"
output = "Color"
prompt_template = """
Remind me of the colors of the {{ _nb_output }} original power rangers.
"""
llm = "llm_for_creative_writing"
nb_output = 5

[pipe.alltime_power_ranger_colors]
type = "PipeLLM"
description = "Recall the colors of all the power rangers"
output = "Color"
prompt_template = """
Remind me of the colors of all the power rangers over all series.
Don't list the names of the characters or the name of the series: just list the colors.
"""
llm = "llm_for_creative_writing"

[pipe.imagine_nature_product]
type = "PipeLLM"
description = "Imagine a product of nature"
inputs = { color = "Color" }
output = "ProductOfNature"
prompt_template = """
Propose a product of nature of this color: $color.
Just state what it is in a single sentence.
"""

[pipe.imagine_fantasy_scene_including_products_of_nature]
type = "PipeLLM"
description = "Imagine a fantasy scene including products of nature"
inputs = { product_of_nature = "ProductOfNature" }
output = "images.ImgGenPrompt"
prompt_template = """
Imagine a fantasy scene including the following products of nature:

@product_of_nature

Keep it short and concise, just one sentence.
"""

[pipe.imagine_nature_scene_of_original_power_rangers_colors]
type = "PipeSequence"
description = "Imagine nature scenes of Power Rangers colors"
output = "images.ImgGenPrompt"
steps = [
    { pipe = "original_power_ranger_colors", result = "color" },
    { pipe = "imagine_nature_product", result = "product_of_nature" },
    { pipe = "imagine_fantasy_scene_including_products_of_nature" },
]

[pipe.imagine_nature_scene_of_alltime_power_rangers_colors]
type = "PipeSequence"
description = "Imagine nature scenes of Power Rangers colors"
output = "images.ImgGenPrompt"
steps = [
    { pipe = "alltime_power_ranger_colors", result = "color", multiple_output = true },
    { pipe = "imagine_nature_product", result = "product_of_nature" },
    { pipe = "imagine_fantasy_scene_including_products_of_nature" },
]

