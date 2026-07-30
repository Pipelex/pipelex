from typing import TYPE_CHECKING

import pytest

from pipelex.libraries.concept.concept_library import ConceptLibrary

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def renderer_concept_library(mocker: "MockerFixture") -> ConceptLibrary:
    """Give the output renderer a real concept library without booting a method.

    The renderer resolves each declared concept's structure class through the loaded method's
    library, and these tests drive it with mock pipes rather than a loaded method. An empty
    `ConceptLibrary` is the honest stand-in: it holds no concepts but resolves any class the
    process registry already has, which is all the rendering needs.
    """
    concept_library = ConceptLibrary.make_empty()
    mocker.patch("pipelex.pipe_machinery.rendering.output_renderer.get_concept_library", return_value=concept_library)
    return concept_library
