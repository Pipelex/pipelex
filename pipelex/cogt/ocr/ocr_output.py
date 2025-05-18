from typing import Dict, List, Optional

from pydantic import BaseModel


class OcrExtractedImage(BaseModel):
    uri: str
    base_64: Optional[str] = None
    caption: Optional[str] = None


class Page(BaseModel):
    text: Optional[str] = None
    images: List[OcrExtractedImage] = []
    screenshot: Optional[OcrExtractedImage] = None


class OcrOutput(BaseModel):
    pages: Dict[int, Page]
