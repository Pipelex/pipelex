import pytest

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.temporal.tprl_content_generation.content_generator_child_factory import ContentGeneratorChildFactory
from pipelex.temporal.tprl_content_generation.content_generator_top_factory import ContentGeneratorTopFactory


@pytest.mark.temporal
class TestTprlMakeContentGenerator:
    def test_tprl_make_content_generator_top(self, generated_content_factory: GeneratedContentFactory):
        crafter = ContentGeneratorTopFactory.make_content_generator_top(
            generated_content_factory=generated_content_factory,
        )
        assert crafter

    def test_tprl_make_content_generator_child(self, generated_content_factory: GeneratedContentFactory):
        crafter = ContentGeneratorChildFactory.make_content_generator_child(
            generated_content_factory=generated_content_factory,
        )
        assert crafter
