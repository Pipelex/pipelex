from typing import List

import pytest
from pydantic import BaseModel

from pipelex import pretty_print
from pipelex.client.client import PipelexClient
from pipelex.client.protocol import PipelineState
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory


class Example(BaseModel):
    pipe_code: str
    memory: List[Stuff]


@pytest.mark.pipelex_api
@pytest.mark.asyncio(loop_scope="class")
class TestPipelexApiClient:
    @pytest.fixture
    def examples(self) -> List[Example]:
        """
        Fixture providing test example for API client tests.
        """
        return [
            Example(
                pipe_code="retrieve_excerpts",
                memory=[
                    StuffFactory.make_stuff(
                        concept_str="Text",
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
                            """
                        ),
                    ),
                    StuffFactory.make_stuff(
                        concept_str="answer.Question",
                        name="question",
                        content=TextContent(text="Aerodynamic features?"),
                    ),
                ],
            ),
        ]

    async def test_client_execute_pipeline(
        self,
        examples: List[Example],
    ):
        """
        Test the execute_pipe method with the example.

        Args:
            examples: List of test examples from the fixture
        """
        for example in examples:
            # Create working memory from example data
            memory = WorkingMemory()
            for stuff in example.memory:
                memory.add_new_stuff(name=stuff.stuff_name or stuff.concept_code, stuff=stuff)

            # Execute pipe
            client = PipelexClient()
            result = await client.execute_pipeline(
                pipe_code=example.pipe_code,
                working_memory=memory,
            )
            pretty_print(result)

            # Verify result
            assert result.pipeline_run_id is not None
            assert result.pipeline_state == PipelineState.COMPLETED
            assert result.pipe_output is not None
