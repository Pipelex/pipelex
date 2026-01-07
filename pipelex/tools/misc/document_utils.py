from pipelex.types import StrEnum


class DocumentFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"

    @property
    def is_pdf(self) -> bool:
        match self:
            case DocumentFormat.PDF:
                return True
            case DocumentFormat.DOCX | DocumentFormat.PPTX:
                return False

    @property
    def is_docx(self) -> bool:
        match self:
            case DocumentFormat.DOCX:
                return True
            case DocumentFormat.PDF | DocumentFormat.PPTX:
                return False

    @property
    def is_pptx(self) -> bool:
        match self:
            case DocumentFormat.PPTX:
                return True
            case DocumentFormat.PDF | DocumentFormat.DOCX:
                return False

    @property
    def as_file_extension(self) -> str:
        match self:
            case DocumentFormat.PDF:
                return "pdf"
            case DocumentFormat.DOCX:
                return "docx"
            case DocumentFormat.PPTX:
                return "pptx"

    @property
    def as_mime_type(self) -> str:
        match self:
            case DocumentFormat.PDF:
                return "application/pdf"
            case DocumentFormat.DOCX:
                return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            case DocumentFormat.PPTX:
                return "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    @classmethod
    def get_supported_mime_types(cls) -> frozenset[str]:
        """Return the set of supported document MIME types."""
        return frozenset(fmt.as_mime_type for fmt in cls)

    @classmethod
    def is_supported_mime_type(cls, mime_type: str) -> bool:
        """Check if a string is a supported document MIME type."""
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
            msg = f"Unsupported document MIME type: {mime_type}. Supported types are: {supported}"
            raise ValueError(msg)

    @classmethod
    def from_mime_type(cls, mime_type: str) -> "DocumentFormat":
        """Get DocumentFormat from a MIME type string.

        Args:
            mime_type: The MIME type to convert.

        Returns:
            The corresponding DocumentFormat.

        Raises:
            ValueError: If the MIME type is not supported.
        """
        for fmt in cls:
            if fmt.as_mime_type == mime_type:
                return fmt
        cls.raise_if_unsupported_mime_type(mime_type)
        # This line is unreachable but needed for type checker
        msg = f"Unsupported MIME type: {mime_type}"
        raise ValueError(msg)
