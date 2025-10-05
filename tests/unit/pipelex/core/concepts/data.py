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


class GalleryWithImageList(StructuredContent):
    """A gallery with a list of images."""

    title: TextContent
    photos: list[ImageContent]


class PersonWithImageTuple(StructuredContent):
    """A person with a tuple of images (before/after photos)."""

    name: TextContent
    before_after: tuple[ImageContent, ImageContent]


class PhotoAlbumItem(StructuredContent):
    """An item in a photo album with nested image."""

    photo: ImageContent
    caption: TextContent


class PhotoAlbumWithNestedImages(StructuredContent):
    """A photo album with a list of items that contain nested images."""

    title: TextContent
    album_items: list[PhotoAlbumItem]


class MediaFrame(StructuredContent):
    """A frame containing an image."""

    frame_image: ImageContent
    border_style: TextContent


class MediaSection(StructuredContent):
    """A section with multiple frames."""

    section_title: TextContent
    frames: list[MediaFrame]


class MediaCollection(StructuredContent):
    """A collection with sections and thumbnails."""

    collection_name: TextContent
    thumbnail: ImageContent
    sections: list[MediaSection]


class ComplexNestedGallery(StructuredContent):
    """A deeply nested gallery structure.

    Structure: list[tuple[MediaCollection, list[PhotoAlbumItem]]]
    This tests:
    - list containing tuples
    - tuples containing objects with nested images
    - objects containing lists of objects with images
    - multiple levels of nesting (4+ levels deep)
    """

    title: TextContent
    # Each gallery entry is a tuple of (collection, album_items)
    # collection has: thumbnail + sections -> frames -> frame_image
    # album_items are PhotoAlbumItem with photo field
    gallery_entries: list[tuple[MediaCollection, list[PhotoAlbumItem]]]


class TestData:
    """Test data for find_nested_image_fields_in_structure_class tests."""

    DOMAIN: ClassVar[str] = "test_images"

    # Test content instances
    SAMPLE_IMAGE: ClassVar[ImageContent] = ImageContent(url="https://example.com/photo.jpg", base_64="base64data")
    SAMPLE_TEXT: ClassVar[TextContent] = TextContent(text="John Doe")
    SAMPLE_BIO: ClassVar[TextContent] = TextContent(text="Software engineer")
    COMPANY_NAME: ClassVar[TextContent] = TextContent(text="Tech Corp")
    LOGO_IMAGE: ClassVar[ImageContent] = ImageContent(url="https://example.com/logo.png", base_64="logobase64")
    TITLE_TEXT: ClassVar[TextContent] = TextContent(text="Company Profile")
