domain = "test_image_inputs"
description = "Test domain for verifying image input functionality"

[concept]
Article = "Article"

[pipe]
[pipe.extract_article_from_image]
type = "PipeLLM"
description = "Describe a page content"
inputs = { image = "Image" }
output = "Article"
system_prompt = """
You are an expert at describing page contents.
"""
prompt = """
Extract the full text (all the text that represents a "title") and the date of the article in the image.
@image
"""

[pipe.describe_page]
type = "PipeLLM"
description = "Describe a page"
inputs = { "page.page_view" = "Image", page = "Page" }
output = "Article"
system_prompt = """
You are an expert at describing page contents.
"""
prompt = """
Extract the date and title.

@page.page_view

Also, add this to the description:
$page.text_and_images.text.text
"""

