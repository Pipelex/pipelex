from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow


class ContentGeneratorInWorkflowFactory:
    @classmethod
    def make_content_generator_in_workflow(cls) -> ContentGeneratorInWorkflow:
        return ContentGeneratorInWorkflow()
