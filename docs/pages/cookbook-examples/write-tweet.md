# Example: Tweet Optimizer

This example demonstrates how to create a pipeline that takes a draft of a tweet and a desired writing style, and then generates an optimized tweet. This is a practical example of "style transfer" for text.

## Get the code

[**➡️ View on GitHub: examples/wip/write_tweet.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/wip/write_tweet.py)

## The Pipeline Explained

The `optimize_tweet` function is the core of this example. It takes two strings, `draft_tweet` and `writing_style`, and executes the `optimize_tweet_sequence` pipeline, passing both inputs through the `input_memory` dictionary with their respective concept specifications.

```python
async def optimize_tweet(draft_tweet: str, writing_style: str) -> str:
    pipe_output = await execute_pipeline(
        pipe_code="optimize_tweet_sequence",
        input_memory={
            "draft_tweet": {
                "concept": "tech_tweet.DraftTweet",
                "content": draft_tweet,
            },
            "writing_style": {
                "concept": "tech_tweet.WritingStyle",
                "content": writing_style,
            },
        },
    )

    # Get the optimized tweet
    optimized_tweet = pipe_output.main_stuff_as_str
    return optimized_tweet
```

This example shows how to use multiple inputs to guide the generation process and produce text that adheres to a specific style.

## The Data Structure: `OptimizedTweet` Model

The data model for this pipeline is very simple, as the final output is just a piece of text. However, the pipeline uses several concepts internally to manage the workflow, such as `DraftTweet`, `TweetAnalysis`, and `WritingStyle`.

```python
class OptimizedTweet(TextContent):
    """A tweet optimized for Twitter/X engagement following best practices."""
    pass
```

## The Pipeline Definition: `tech_tweet.plx`

This pipeline uses a two-step "analyze and optimize" sequence. The first pipe analyzes the draft tweet for common pitfalls, and the second pipe rewrites the tweet based on the analysis and a provided writing style. This is a powerful pattern for refining generated content.

```plx
[pipe.optimize_tweet_sequence]
type = "PipeSequence"
description = "Analyze and optimize a tech tweet in sequence"
inputs = { draft_tweet = "DraftTweet", writing_style = "WritingStyle" }
output = "OptimizedTweet"
steps = [
    # First, analyze the draft tweet for issues like "fluffiness" and "vagueness".
    { pipe = "analyze_tweet", result = "tweet_analysis" },
    # Then, optimize the tweet based on the analysis and the desired writing style.
    { pipe = "optimize_tweet", result = "optimized_tweet" },
]

# This is the pipe that analyzes the draft tweet.
[pipe.analyze_tweet]
type = "PipeLLM"
description = "Analyze the draft tweet and identify areas for improvement"
inputs = { draft_tweet = "DraftTweet" }
output = "TweetAnalysis"
system_prompt = """
You are an expert in social media optimization, particularly for tech content on Twitter/X.
Your role is to analyze tech tweets and check if they display typical startup communication pitfalls.
"""
prompt = """
Evaluate the tweet for these key issues:

**Fluffiness** - Overuse of buzzwords without concrete meaning...
**Cringiness** - Content that induces secondhand embarrassment...
**Humblebragginess** - Disguising boasts as casual updates...
**Vagueness** - Failing to clearly communicate what the product/service actually does...

@draft_tweet
"""
```
This "analyze and refine" pattern is a great way to build more reliable and sophisticated text generation workflows. The first step provides a structured critique, and the second step uses that critique to improve the final output.

Here is the flowchart generated during this run:

```mermaid
---
config:
  layout: dagre
  theme: base
---
flowchart LR
    subgraph "optimize_tweet_sequence"
    direction LR
        FGunn["draft_tweet:<br>**Draft tweet**"]
        EWhtJ["tweet_analysis:<br>**Tweet analysis**"]
        65Eb2["optimized_tweet:<br>**Optimized tweet**"]
        i34D5["writing_style:<br>**Writing style**"]
    end
class optimize_tweet_sequence sub_a;

    classDef sub_a fill:#e6f5ff,color:#333,stroke:#333;

    classDef sub_b fill:#fff5f7,color:#333,stroke:#333;

    classDef sub_c fill:#f0fff0,color:#333,stroke:#333;
    FGunn -- "Analyze tweet" ----> EWhtJ
    FGunn -- "Optimize tweet" ----> 65Eb2
    EWhtJ -- "Optimize tweet" ----> 65Eb2
    i34D5 -- "Optimize tweet" ----> 65Eb2
```
