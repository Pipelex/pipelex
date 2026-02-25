import io

from PIL import Image

from pipelex.types import StrEnum


class ImageFormat(StrEnum):
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"

    @property
    def is_transparent_compatible(self) -> bool:
        match self:
            case ImageFormat.PNG:
                return True
            case ImageFormat.JPEG | ImageFormat.WEBP:
                return False

    @property
    def is_png(self) -> bool:
        match self:
            case ImageFormat.PNG:
                return True
            case ImageFormat.JPEG | ImageFormat.WEBP:
                return False

    @property
    def is_jpeg(self) -> bool:
        match self:
            case ImageFormat.JPEG:
                return True
            case ImageFormat.PNG | ImageFormat.WEBP:
                return False

    @property
    def as_file_extension(self) -> str:
        match self:
            case ImageFormat.PNG:
                return "png"
            case ImageFormat.JPEG:
                return "jpg"
            case ImageFormat.WEBP:
                return "webp"

    @property
    def as_mime_type(self) -> str:
        match self:
            case ImageFormat.PNG:
                return "image/png"
            case ImageFormat.JPEG:
                return "image/jpeg"
            case ImageFormat.WEBP:
                return "image/webp"

    @classmethod
    def from_mime_type(cls, mime_type: str) -> "ImageFormat":
        for fmt in cls:
            if fmt.as_mime_type == mime_type:
                return fmt
        cls.raise_if_unsupported_mime_type(mime_type)
        msg = f"Unsupported MIME type: {mime_type}"
        raise ValueError(msg)

    @classmethod
    def get_supported_mime_types(cls) -> frozenset[str]:
        """Return the set of supported image MIME types."""
        return frozenset(fmt.as_mime_type for fmt in cls)

    @classmethod
    def is_supported_mime_type(cls, mime_type: str) -> bool:
        """Check if a string is a supported image MIME type."""
        return mime_type in cls.get_supported_mime_types()

    @classmethod
    def raise_if_unsupported_mime_type(cls, mime_type: str) -> None:
        """Validate that a MIME type is supported.

        Args:
            mime_type: The MIME type to validate.

        Raises:
            ValueError: If the MIME type is not supported.
        """
        if not cls.is_supported_mime_type(mime_type):
            supported = ", ".join(sorted(cls.get_supported_mime_types()))
            if mime_type.startswith("image/"):
                msg = f"Unsupported image MIME type: {mime_type}. Supported types are: {supported}"
            else:
                msg = f"Invalid image MIME type: {mime_type}. Expected format 'image/<subtype>'. Supported types are: {supported}"
            raise ValueError(msg)


def pil_image_to_bytes(pil_image: Image.Image, image_format: ImageFormat | None) -> bytes:
    """Convert a PIL Image to bytes in the specified format.

    Args:
        pil_image: The PIL Image to convert
        image_format: The desired output format (PNG, JPEG, or WEBP)

    Returns:
        The image as bytes in the specified format
    """
    buffer = io.BytesIO()
    pil_format: str
    image_format = image_format or ImageFormat.PNG
    match image_format:
        case ImageFormat.PNG:
            pil_format = "PNG"
        case ImageFormat.JPEG:
            pil_format = "JPEG"
        case ImageFormat.WEBP:
            pil_format = "WEBP"

    pil_image.save(buffer, format=pil_format)
    return buffer.getvalue()
