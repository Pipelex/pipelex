"""Unit tests for the shaper's D3 file-path arm: bare relative local paths for Image/Document-
refining inputs resolve against ``inputs_base_dir`` (the inputs file's parent, threaded from the
CLI). Absolute paths, remote/scheme URLs, and the ``{"url": ...}`` dict form (owned by the CLI's
signature-blind url-key walk) are never rewritten.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.list_content import ListContent
from pipelex.method_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import Exhibit, Photo, build_input_specs

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent


class TestInputShaperFilePaths:
    def test_bare_relative_path_resolves_against_base_dir(self, tmp_path: Path):
        """A bare relative path for an Image-refining input becomes the base_dir-resolved path."""
        input_specs = build_input_specs([("photo", "shaper_test.Photo", None)])
        working_memory = InputShaper.shape(
            {"photo": "photo.jpg"}, input_specs=input_specs, inputs_base_dir=tmp_path, concept_provider=get_concept_library()
        )

        photo_stuff = working_memory.get_stuff("photo")
        assert photo_stuff.concept.concept_ref == "shaper_test.Photo"
        assert isinstance(photo_stuff.content, Photo)
        assert photo_stuff.content.url == str(tmp_path / "photo.jpg")

    def test_bare_absolute_path_untouched(self, tmp_path: Path):
        """An absolute path is never rewritten, base_dir or not."""
        absolute_path = str(tmp_path / "elsewhere" / "photo.jpg")
        input_specs = build_input_specs([("photo", "shaper_test.Photo", None)])
        working_memory = InputShaper.shape(
            {"photo": absolute_path}, input_specs=input_specs, inputs_base_dir=tmp_path, concept_provider=get_concept_library()
        )

        photo_stuff = working_memory.get_stuff("photo")
        assert isinstance(photo_stuff.content, Photo)
        assert photo_stuff.content.url == absolute_path

    def test_bare_relative_path_without_base_dir_untouched(self):
        """No base_dir (in-process / inline-JSON callers): a relative path keeps today's CWD contract."""
        input_specs = build_input_specs([("photo", "shaper_test.Photo", None)])
        working_memory = InputShaper.shape({"photo": "photo.jpg"}, input_specs=input_specs, concept_provider=get_concept_library())

        photo_stuff = working_memory.get_stuff("photo")
        assert isinstance(photo_stuff.content, Photo)
        assert photo_stuff.content.url == "photo.jpg"

    @pytest.mark.parametrize(
        "url_value",
        [
            "https://example.com/photo.jpg",
            "s3://bucket/photo.jpg",
            "data:image/png;base64,iVBORw0KGgo=",
            "pipelex-storage://objects/photo.jpg",
        ],
    )
    def test_remote_and_scheme_urls_untouched(self, tmp_path: Path, url_value: str):
        """Remote URLs and scheme-qualified URIs are not local paths — never rewritten."""
        input_specs = build_input_specs([("photo", "shaper_test.Photo", None)])
        working_memory = InputShaper.shape(
            {"photo": url_value}, input_specs=input_specs, inputs_base_dir=tmp_path, concept_provider=get_concept_library()
        )

        photo_stuff = working_memory.get_stuff("photo")
        assert isinstance(photo_stuff.content, Photo)
        assert photo_stuff.content.url == url_value

    def test_list_items_resolve_element_wise(self, tmp_path: Path):
        """Each bare relative item of a Document[] input resolves; absolute items stay untouched."""
        absolute_path = str(tmp_path / "other" / "b.pdf")
        input_specs = build_input_specs([("exhibits", "shaper_test.Exhibit", True)])
        working_memory = InputShaper.shape(
            {"exhibits": ["a.pdf", absolute_path]}, input_specs=input_specs, inputs_base_dir=tmp_path, concept_provider=get_concept_library()
        )

        exhibits_stuff = working_memory.get_stuff("exhibits")
        assert exhibits_stuff.concept.concept_ref == "shaper_test.Exhibit"
        exhibits_content: StuffContent = exhibits_stuff.content
        assert isinstance(exhibits_content, ListContent)
        items = cast("ListContent[StuffContent]", exhibits_content).items
        assert [item.url for item in items if isinstance(item, Exhibit)] == [str(tmp_path / "a.pdf"), absolute_path]

    def test_url_dict_form_not_reresolved_by_shaper(self, tmp_path: Path):
        """The {"url": ...} dict form is owned by the CLI's url-key walk — the shaper leaves it as-is."""
        value: dict[str, Any] = {"url": "photo.jpg"}
        input_specs = build_input_specs([("photo", "shaper_test.Photo", None)])
        working_memory = InputShaper.shape(
            {"photo": value}, input_specs=input_specs, inputs_base_dir=tmp_path, concept_provider=get_concept_library()
        )

        photo_stuff = working_memory.get_stuff("photo")
        assert isinstance(photo_stuff.content, Photo)
        assert photo_stuff.content.url == "photo.jpg"

    def test_bare_tilde_path_expands_to_home_not_base_dir(self, tmp_path: Path):
        """A ~-prefixed path is home-anchored: it expands to the home dir, never joined onto base_dir."""
        input_specs = build_input_specs([("photo", "shaper_test.Photo", None)])
        working_memory = InputShaper.shape(
            {"photo": "~/photo.jpg"}, input_specs=input_specs, inputs_base_dir=tmp_path, concept_provider=get_concept_library()
        )

        photo_stuff = working_memory.get_stuff("photo")
        assert isinstance(photo_stuff.content, Photo)
        assert photo_stuff.content.url == str(Path("~/photo.jpg").expanduser())

    def test_bare_tilde_path_expands_without_base_dir(self):
        """No base_dir: a ~-prefixed path still expands to home (~ is home-anchored, not CWD-relative)."""
        input_specs = build_input_specs([("photo", "shaper_test.Photo", None)])
        working_memory = InputShaper.shape({"photo": "~/photo.jpg"}, input_specs=input_specs, concept_provider=get_concept_library())

        photo_stuff = working_memory.get_stuff("photo")
        assert isinstance(photo_stuff.content, Photo)
        assert photo_stuff.content.url == str(Path("~/photo.jpg").expanduser())
