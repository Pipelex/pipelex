import pytest
from pydantic import BaseModel

from pipelex import pretty_print
from pipelex.client.client import PipelexClient
from pipelex.client.protocol import PipelineState
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent


class Example(BaseModel):
    pipe_code: str
    memory: list[Stuff]


@pytest.mark.pipelex_api
@pytest.mark.asyncio(loop_scope="class")
class TestPipelexApiClient:
    @pytest.fixture
    def examples(self) -> list[Example]:
        """Fixture providing test example for API client tests."""
        return [
            Example(
                pipe_code="retrieve_excerpts",
                memory=[
                    StuffFactory.make_stuff(
                        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                        name="text",
                        content=TextContent(
                            text="""
                                The Dawn of Ultra-Rapid Transit: NextGen High-Speed Trains Redefine Travel
                                By Eliza Montgomery, Transportation Technology Reporter

                                In an era where time is increasingly precious, a revolution in rail transportation is quietly
                                transforming how we connect cities and regions. The emergence of ultra-high-speed train
                                networks, capable of speeds exceeding 350 mph, promises to render certain short-haul
                                flights obsolete while dramatically reducing carbon emissions.

                                QuantumRail's Breakthrough Technology
                                Leading this transportation revolution is QuantumRail Technologies, whose new MagLev-X
                                platform has shattered previous speed records during recent tests in Nevada's
                                Velocity Valley testinggrounds. The train achieved a remarkable 368 mph,
                                maintaining this speed for over fifteen minutes.

                                'What we're seeing isn't just an incremental improvement—it's a fundamental shift
                                in transportationphysics,' explains Dr. Hiroshi Takahashi, Chief Engineer at
                                QuantumRail. 'The MagLev-X's superconducting magnets and aerodynamic profile
                                allow us to overcome limitations that have constrained train speeds for decades.'

                                Economic Implications
                                The introduction of these next-generation trains isn't merely a technical
                                achievement—it represents a potential economic windfall for connected regions.
                                The TransContinental Alliance, a consortium of cities supporting high-speed rail
                                development, estimates that new high-speed corridors could generate $87
                                billion in economic activity over the next decade.

                                'When you can travel between Chicago and Detroit in under an hour,
                                you're essentially creating a single economic zone, notes Dr. Amara Washington,
                                economist at the Urban Mobility Institute. This transforms labor markets, housing
                                patterns, and business relationships.

                                WindStream's Competitive Response
                                Not to be outdone, European manufacturer WindStream Mobility has unveiled
                                its own ultra-high-speed platform, the AeroGlide TGV-7. Featuring a
                                distinctive bionic design inspired by peregrine falcons, the train uses an innovative
                                hybrid propulsion system that combines traditional electric motors with
                                compressed air boosters for acceleration phases.
                            """,
                        ),
                    ),
                    StuffFactory.make_stuff(
                        concept=ConceptFactory.make(
                            concept_code="Question",
                            domain="answer",
                            description="answer.Question",
                            structure_class_name="Question",
                        ),
                        name="question",
                        content=TextContent(text="Aerodynamic features?"),
                    ),
                ],
            ),
        ]

    async def test_client_execute_pipeline(
        self,
        examples: list[Example],
    ):
        """Test the execute_pipe method with the example.

        Args:
            examples: List of test examples from the fixture

        """
        for example in examples:
            # Create working memory from example data
            question = example.memory[1]
            text = example.memory[0]
            memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=[question, text], main_name=text.stuff_name or text.concept.code)

            # Execute pipe
            client = PipelexClient()
            pipeline_reponse = await client.execute_pipeline(
                pipe_code=example.pipe_code,
                working_memory=memory,
            )

            pretty_print(pipeline_reponse, title="PIPELINE RESPONSE")
            # Verify result
            assert pipeline_reponse.pipe_output
            assert pipeline_reponse.pipe_output.pipeline_run_id is not None
            assert pipeline_reponse.pipeline_state == PipelineState.COMPLETED
            assert pipeline_reponse.pipe_output is not None

            working_memory = pipeline_reponse.pipe_output.working_memory
            pretty_print(working_memory, title="WORKING MEMORY")

            # Verify question structure
            assert working_memory.root["question"].content["text"] == "Aerodynamic features?"

            # Verify main_stuff structure
            assert working_memory.root["main_stuff"] is not None
            assert working_memory.root["main_stuff"].concept == "retrieve.RetrievedExcerpt"
            assert working_memory.root["main_stuff"].content is not None
            assert len(working_memory.root["main_stuff"].content) > 0

            # Verify text structure
            assert "The Dawn of Ultra-Rapid Transit" in working_memory.root["text"].content["text"]
