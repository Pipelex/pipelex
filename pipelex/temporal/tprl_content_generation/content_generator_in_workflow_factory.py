from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow


class ContentGeneratorInWorkflowFactory:
    @classmethod
    def make_content_generator_in_workflow(
        cls,
        generated_content_factory: GeneratedContentFactory,
    ) -> ContentGeneratorInWorkflow:
        return ContentGeneratorInWorkflow(generated_content_factory=generated_content_factory)
