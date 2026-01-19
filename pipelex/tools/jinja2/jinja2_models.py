from pipelex.types import StrEnum


class Jinja2FilterName(StrEnum):
    FORMAT = "format"
    TAG = "tag"
    ESCAPE_SCRIPT_TAG = "escape_script_tag"
    WITH_IMAGES = "with_images"


class Jinja2ContextKey(StrEnum):
    TAG_STYLE = "tag_style"
    TEXT_FORMAT = "text_format"
    IMAGE_REGISTRY = "image_registry"
