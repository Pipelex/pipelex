

domain = "documents"
description = "The domain of documents that can comprise pages, text, images, etc. in PDF or other formats"

[concept]
TextAndImagesContent = "A content that comprises text and images where the text can include local links to the images"

[pipe]
# PipeExtract requires to have a single input
# It can be named however you want
# but it must be either an image or a pdf or a concept which refines one of them
[pipe.extract_page_contents_from_pdf]
type = "PipeExtract"
description = "Extract page contents from a PDF document"
inputs = { document = "PDF" }
output = "Page"
page_images = true
page_views = false

[pipe.extract_page_contents_and_views_from_pdf]
type = "PipeExtract"
description = "Extract page contents from a PDF document as well as full page views"
inputs = { document = "PDF" }
output = "Page"
page_images = true
page_views = true

