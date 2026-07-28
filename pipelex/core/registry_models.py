from typing import ClassVar

from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.dynamic_content import DynamicContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.system.registries.registry_base import ModelType, RegistryModels


class CoreRegistryModels(RegistryModels):
    """Core's value model, as one boot-time registration manifest.

    The pipe kinds and their factories used to live here too; they now live in
    ``pipelex.pipe_machinery.registry_models.PipeRegistryModels``, which is what keeps ``core/``
    free of ``pipe_operators`` / ``pipe_controllers`` / ``pipe_signature`` imports. Both manifests
    are registered side by side at boot; they must stay disjoint.
    """

    FIELD_EXTRACTION: ClassVar[list[ModelType]] = []

    STUFF: ClassVar[list[ModelType]] = [
        TextContent,
        NumberContent,
        YesNoContent,
        DateContent,
        TimeContent,
        ImageContent,
        Stuff,
        StuffContent,
        HtmlContent,
        ListContent,
        StructuredContent,
        DocumentContent,
        TextAndImagesContent,
        PageContent,
        JSONContent,
        SearchResultContent,
        CompositeContent,
    ]

    EXPERIMENTAL: ClassVar[list[ModelType]] = [
        DynamicContent,
    ]
