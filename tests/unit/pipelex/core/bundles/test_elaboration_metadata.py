from pipelex.core.bundles.pipelex_bundle_blueprint import ElaborationMetadata, PipelexBundleBlueprint, StepRole
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestElaborationMetadata:
    def test_round_trip_through_dump_and_validate(self):
        metadata = ElaborationMetadata(parent_pipe_code="my_parent", step_role=StepRole.DRAFT_TEXT)
        dumped = metadata.model_dump()
        restored = ElaborationMetadata.model_validate(dumped)
        assert restored.parent_pipe_code == "my_parent"
        assert restored.step_role is StepRole.DRAFT_TEXT

    def test_bundle_dump_excludes_elaboration_metadata(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="A bundle for testing",
            concept={},
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="A pipe",
                    output="Text",
                    prompt="Hello",
                ),
            },
            elaboration_metadata={
                "my_pipe__draft_text": ElaborationMetadata(parent_pipe_code="my_pipe", step_role=StepRole.DRAFT_TEXT),
            },
        )
        dumped = bundle.model_dump()
        assert "elaboration_metadata" not in dumped

    def test_get_elaboration_for_returns_metadata(self):
        metadata = ElaborationMetadata(parent_pipe_code="my_parent", step_role=StepRole.STRUCTURE)
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="A bundle for testing",
            elaboration_metadata={"my_parent__structure": metadata},
        )
        result = bundle.get_elaboration_for(pipe_code="my_parent__structure")
        assert result is metadata

    def test_get_elaboration_for_returns_none_when_unknown(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="A bundle for testing",
        )
        assert bundle.get_elaboration_for(pipe_code="anything") is None

    def test_get_elaboration_for_returns_none_when_user_authored(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="A bundle for testing",
            elaboration_metadata={
                "my_pipe__draft_text": ElaborationMetadata(parent_pipe_code="my_pipe", step_role=StepRole.DRAFT_TEXT),
            },
        )
        assert bundle.get_elaboration_for(pipe_code="my_pipe") is None
