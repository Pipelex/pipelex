from abc import ABC, abstractmethod

from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent


class FetchWorkerAbstract(ABC):
    @abstractmethod
    async def fetch_url(
        self,
        url: str,
        include_raw_html: bool | None = None,
        render_js: bool | None = None,
        extract_images: bool | None = None,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> TextAndImagesContent:
        """Fetch and clean the content of a web page, returning text and optionally images.

        Args:
            url: The URL of the web page to fetch
            include_raw_html: Whether to include the raw HTML of the webpage in the response
            render_js: Whether to render the JavaScript of the webpage before fetching
            extract_images: Whether to extract images from the webpage
            timeout: The timeout for the HTTP request, in seconds

        Returns:
            TextAndImagesContent with the fetched page content
        """
