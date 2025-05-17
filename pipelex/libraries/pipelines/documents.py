# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pipelex.core.stuff_content import ImageContent, StructuredContent, TextAndImagesContent


class PageContent(StructuredContent):
    text_and_images: TextAndImagesContent
    screenshot: Optional[ImageContent] = None
