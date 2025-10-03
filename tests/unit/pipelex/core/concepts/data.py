"""Test data and structures for stuff tests."""

from typing import ClassVar

from pipelex.core.stuffs.stuff_content import ImageContent, StructuredContent, TextContent


# Test structures
class ProfilePhoto(ImageContent):
    """A profile photo that refines Image."""


class PersonWithDirectImage(StructuredContent):
    """A person with a direct image field."""

    name: TextContent
    photo: ImageContent


class PersonWithRefinedImage(StructuredContent):
    """A person with a refined image field."""

    name: TextContent
    profile_photo: ProfilePhoto


class PersonWithText(StructuredContent):
    """A person with only text, no images."""

    name: TextContent
    bio: TextContent


class CompanyInfo(StructuredContent):
    """Company info with nested person."""

    company_name: TextContent
    ceo: PersonWithDirectImage


class NestedComplex(StructuredContent):
    """Complex nested structure with multiple levels."""

    title: TextContent
    company: CompanyInfo
    logo: ImageContent


class PersonWithOptionalImage(StructuredContent):
    """A person with an optional image field."""

    name: TextContent
    photo: ImageContent | None = None


class TestData:
    """Test data for find_image_field_paths tests."""

    DOMAIN: ClassVar[str] = "test_images"

    # Test content instances
    SAMPLE_IMAGE: ClassVar[ImageContent] = ImageContent(url="https://example.com/photo.jpg", base_64="base64data")
    SAMPLE_TEXT: ClassVar[TextContent] = TextContent(text="John Doe")
    SAMPLE_BIO: ClassVar[TextContent] = TextContent(text="Software engineer")
    COMPANY_NAME: ClassVar[TextContent] = TextContent(text="Tech Corp")
    LOGO_IMAGE: ClassVar[ImageContent] = ImageContent(url="https://example.com/logo.png", base_64="logobase64")
    TITLE_TEXT: ClassVar[TextContent] = TextContent(text="Company Profile")
