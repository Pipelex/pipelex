"""End-to-end coverage for file-ish Smart Inputs (Phase 3, D3 + D11).

Through the real runner (dry mode), a bare relative path for a declared `Photo` (Image-refining)
input resolves against `inputs_base_dir` — the seam value the CLI derives from the inputs file's
parent directory — and builds an `ImageContent`; a list of bare paths shapes element-wise into
`ListContent[Exhibit]`; and a bare CSV path under a declared `Person[]` reads the table into
`ListContent[Person]` with no envelope. The `{"url": ...}` dict form (what the CLI's url-key walk
delivers: an absolute url) lands on the same resolved result as the bare form.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from pipelex.config import get_config
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent
    from pipelex.system.configuration.configs import PipelineExecutionConfig

_FIXTURE_DIR = Path(__file__).parent / "smart_inputs_files"


def _no_normalize_config() -> "PipelineExecutionConfig":
    """Execution config with data-url→storage normalization off, so the shaper's D3-resolved local
    path stays a filesystem path (normalization would otherwise rewrite it to a pipelex-storage URI
    — a legitimate downstream step, but it would obscure exactly the resolution this test pins).
    """
    return get_config().pipelex.pipeline_execution_config.model_copy(update={"is_normalize_data_urls_to_storage": False})


@pytest.mark.asyncio(loop_scope="class")
class TestSmartInputsFilesDryRun:
    async def test_bare_paths_and_csv_resolve_and_shape(self):
        """Bare relative file paths resolve against inputs_base_dir; a bare CSV reads into Person[]."""
        runner = PipelexMTHDSProtocol(
            library_dirs=[str(_FIXTURE_DIR)],
            pipe_run_mode=PipeRunMode.DRY,
            inputs_base_dir=_FIXTURE_DIR,
            execution_config=_no_normalize_config(),
        )
        inputs: dict[str, Any] = {
            "photo": "photo.jpg",
            "exhibits": ["a.pdf", "b.pdf"],
            "people": "people.csv",
        }
        response = await runner.execute(pipe_code="review_case", inputs=inputs)

        assert response.state == RunState.COMPLETED
        working_memory = response.pipe_output.working_memory

        photo_stuff = working_memory.get_stuff("photo")
        assert photo_stuff.concept.concept_ref == "smart_inputs_files_demo.Photo"
        assert isinstance(photo_stuff.content, ImageContent)
        assert photo_stuff.content.url == str(_FIXTURE_DIR / "photo.jpg")

        exhibits_stuff = working_memory.get_stuff("exhibits")
        assert exhibits_stuff.concept.concept_ref == "smart_inputs_files_demo.Exhibit"
        exhibits_content: StuffContent = exhibits_stuff.content
        assert isinstance(exhibits_content, ListContent)
        exhibit_urls = [item.url for item in cast("ListContent[StuffContent]", exhibits_content).items if isinstance(item, DocumentContent)]
        assert exhibit_urls == [str(_FIXTURE_DIR / "a.pdf"), str(_FIXTURE_DIR / "b.pdf")]

        people_stuff = working_memory.get_stuff("people")
        assert people_stuff.concept.concept_ref == "smart_inputs_files_demo.Person"
        people_content: StuffContent = people_stuff.content
        assert isinstance(people_content, ListContent)
        people_items = cast("ListContent[StuffContent]", people_content).items
        assert len(people_items) == 2
        assert all(isinstance(item, StructuredContent) for item in people_items)
        assert [item.model_dump() for item in people_items] == [
            {"name": "Ada Lovelace", "job": "Mathematician"},
            {"name": "Grace Hopper", "job": "Computer Scientist"},
        ]

    async def test_url_dict_form_matches_bare_form(self):
        """The {"url": <absolute>} dict form (post CLI url-key walk) equals the bare-path result."""
        runner = PipelexMTHDSProtocol(
            library_dirs=[str(_FIXTURE_DIR)],
            pipe_run_mode=PipeRunMode.DRY,
            inputs_base_dir=_FIXTURE_DIR,
            execution_config=_no_normalize_config(),
        )
        inputs: dict[str, Any] = {
            "photo": {"url": str(_FIXTURE_DIR / "photo.jpg")},
            "exhibits": ["a.pdf"],
            "people": {"url": str(_FIXTURE_DIR / "people.csv")},
        }
        response = await runner.execute(pipe_code="review_case", inputs=inputs)

        assert response.state == RunState.COMPLETED
        working_memory = response.pipe_output.working_memory

        photo_stuff = working_memory.get_stuff("photo")
        assert photo_stuff.concept.concept_ref == "smart_inputs_files_demo.Photo"
        assert isinstance(photo_stuff.content, ImageContent)
        assert photo_stuff.content.url == str(_FIXTURE_DIR / "photo.jpg")

        exhibits_stuff = working_memory.get_stuff("exhibits")
        assert exhibits_stuff.concept.concept_ref == "smart_inputs_files_demo.Exhibit"
        exhibits_content: StuffContent = exhibits_stuff.content
        assert isinstance(exhibits_content, ListContent)
        exhibit_urls = [item.url for item in cast("ListContent[StuffContent]", exhibits_content).items if isinstance(item, DocumentContent)]
        assert exhibit_urls == [str(_FIXTURE_DIR / "a.pdf")]

        people_stuff = working_memory.get_stuff("people")
        assert people_stuff.concept.concept_ref == "smart_inputs_files_demo.Person"
        people_content: StuffContent = people_stuff.content
        assert isinstance(people_content, ListContent)
        assert len(cast("ListContent[StuffContent]", people_content).items) == 2
