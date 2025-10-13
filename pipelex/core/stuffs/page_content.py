from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.tools.misc.file_utils import ensure_directory_exists


class PageContent(StructuredContent):
    text_and_images: TextAndImagesContent
    page_view: ImageContent | None = None

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        self.text_and_images.save_to_directory(directory=directory)
        if page_view := self.page_view:
            page_view.save_to_directory(directory=directory, base_name="page_view")
