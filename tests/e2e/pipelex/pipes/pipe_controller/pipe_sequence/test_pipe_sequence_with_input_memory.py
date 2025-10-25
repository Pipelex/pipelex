"""Test pipe sequence with input memory functionality."""

import pytest

from pipelex import pretty_print
from pipelex.pipeline.execute import execute_pipeline
from tests.test_pipelines.test_tweet import OptimizedTweet

SAMPLE_DRAFT_TWEET = """
Local high school basketball star Maria Rodriguez was the talk of Division I scouts - 6'2",
averaging 28 points per game, with offers from Duke, Stanford, and UConn all on the table.
Her single mother worked three jobs to keep them afloat, and a full ride scholarship seemed
like their golden ticket out of poverty.

But Maria saw something else when she looked around her neighborhood in East Oakland. Kids
as young as 8 were getting recruited into gangs because there was literally nothing else to
do after school. The community center had been closed for budget cuts, the local high school's
sports programs were underfunded, and talented kids were falling through the cracks every single day.

So Maria made a decision that shocked everyone: she turned down every scholarship offer and
enrolled at the local community college instead. Her guidance counselor called her crazy. Her mother
cried for weeks. But Maria had a plan.

She started coaching youth basketball teams for free, but knew she needed to leverage cutting-edge
digital transformation strategies to optimize her community impact ecosystem. Maria decided to disrupt
traditional youth development paradigms by creating a revolutionary blockchain-powered, cloud-native
mobile application called "HoopSync" - a next-generation SaaS platform that synergizes basketball
analytics with holistic youth empowerment through machine learning algorithms that predict optimal
mentorship touchpoints while scaling community engagement metrics across multiple verticals.

The app was basically just a group chat where kids could message her about practice times, but Maria's
LinkedIn posts made it sound like she was launching the next unicorn startup. She used phrases like
"pivoting the youth sports landscape through innovative digital solutions" and "monetizing social
impact through strategic technology integration." The cringe factor was off the charts.

Things got ultra-awkward when Maria tried to go viral on TikTok with her "Ball is Life, Tech is Wife"
dance challenge. The video of her doing robot moves while dribbling a basketball in her garage got 47
views (mostly from her mom's different accounts) and became a local meme for all the wrong reasons.
She literally ended every sentence with "periodt bestie" for three months and wore backwards baseball
aps to "connect with the youth demographic."

But somehow, despite the cringey marketing and unnecessarily complicated app that could have been a
simple calendar, Maria's genuine heart shone through. She personally drove kids to tryouts across the
Bay Area, organized weekend tournaments in parking lots, and convinced local businesses to sponsor uniforms.
Within two years, she had created a pipeline that helped 47 kids earn college scholarships - more than
her high school had produced in the previous decade combined.

The real breakthrough came when one of her TikTok fails accidentally went viral (2.3M views of her
tripping while filming a "motivational Monday" video). Instead of hiding, Maria owned the embarrassment
and pivoted it into authentic storytelling about failure and resilience. The authenticity resonated,
leading to corporate partnerships and even NBA players donating equipment after seeing her genuine
mission beyond the tech buzzwords.

Now she's breaking ground on a 15,000 square foot community center funded by the unlikely combination
of her cringe-famous social media presence and the world's most over-engineered youth sports app.
The center will serve 500+ kids annually, and Maria has finally learned that sometimes the best technology
is just showing up with a basketball and genuine care.

Maria's story proves that even the most cringe-worthy execution can't stop authentic purpose, and
that sometimes you have to embrace being the main character of your own embarrassing story to create real change.
"""

SAMPLE_WRITING_STYLE = """
🧵 THREAD: The $20 decision that changed everything

I was broke, living paycheck to paycheck, when I saw a coding bootcamp ad.

$20 for a trial week. I had to choose between that and groceries.

I chose the bootcamp.

Fast forward 18 months:
→ $85k salary
→ Remote work freedom
→ Built apps used by 100k+ people
→ Speaking at conferences

The lesson? Sometimes the scariest decisions lead to the biggest breakthroughs.

What $20 decision are you avoiding right now? 👇

#TechTwitter #CodingJourney #CareerChange
"""


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio
class TestPipeSequenceWithInputMemory:
    """Test pipe sequence functionality with input memory."""

    async def test_optimize_tweet_sequence_with_input_memory(self):
        """Test the optimize_tweet_sequence pipeline using inputs parameter."""
        # Execute the pipeline using inputs
        pipe_output = await execute_pipeline(
            pipe_code="optimize_tweet_sequence",
            inputs={
                "draft_tweet": {
                    "concept": "tech_tweet.DraftTweet",
                    "content": SAMPLE_DRAFT_TWEET,
                },
                "writing_style": {
                    "concept": "tech_tweet.WritingStyle",
                    "content": SAMPLE_WRITING_STYLE,
                },
            },
        )

        # Get the optimized tweet
        optimized_tweet = pipe_output.main_stuff_as(content_type=OptimizedTweet)

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None
        assert optimized_tweet is not None
        assert isinstance(optimized_tweet, OptimizedTweet)
        assert len(optimized_tweet.text) > 0

        # Log output and generate report
        pretty_print(pipe_output, title="Pipe output for optimize_tweet_sequence")

        # Verify the optimized tweet is different from the draft
        assert optimized_tweet.text != SAMPLE_DRAFT_TWEET
        # Verify it's not empty
        assert len(optimized_tweet.text.strip()) > 0
        assert "Maria Rodriguez" in optimized_tweet.text
