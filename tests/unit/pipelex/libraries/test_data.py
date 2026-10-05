from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class CrateQualificationTestData:
    """A crate for the qualification pass, built fresh on each call since a test may change it."""

    @classmethod
    def crate(cls) -> LibraryCrate:
        """A crate carrying one bare ref of every kind the pass advertises."""
        return LibraryCrate(
            concepts={
                "alpha.Category": "a category",
                "alpha.Report": ConceptBlueprint(
                    description="a report",
                    structure={
                        "label": ConceptStructureBlueprint(
                            description="the label",
                            type=ConceptStructureBlueprintFieldType.CONCEPT,
                            concept_ref="Category",
                        ),
                        "tags": ConceptStructureBlueprint(
                            description="the tags",
                            type=ConceptStructureBlueprintFieldType.LIST,
                            item_type=ConceptStructureBlueprintFieldType.CONCEPT,
                            item_concept_ref="Category",
                        ),
                    },
                ),
                "alpha.Detailed": ConceptBlueprint(description="a detailed report", refines="Report"),
            },
            pipes={
                "alpha.leaf": PipeLLMBlueprint(description="leaf", inputs={"item": "Category"}, output="Report", prompt="use $item"),
                "alpha.seq": PipeSequenceBlueprint(description="seq", output="Report", steps=[SubPipeBlueprint(pipe="leaf")]),
                "alpha.par": PipeParallelBlueprint(
                    description="par",
                    output="Composite",
                    branches=[SubPipeBlueprint(pipe="leaf", result="one")],
                ),
                "alpha.cond": PipeConditionBlueprint(
                    description="cond",
                    output="Report",
                    expression="x",
                    outcomes={"hit": "leaf"},
                    default_outcome="leaf",
                ),
                "alpha.batched": PipeBatchBlueprint(
                    description="batch",
                    inputs={"items": "Category[]"},
                    output="Report[]",
                    branch_pipe_code="leaf",
                    input_list_name="items",
                    input_item_name="item",
                ),
            },
            domains={"alpha": DomainBlueprint(code="alpha", description="alpha domain")},
        )
