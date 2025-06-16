# Example: Tweet Optimizer

This example demonstrates how to create a pipeline that takes a draft of a tweet and a desired writing style, and then generates an optimized tweet. This is a practical example of "style transfer" for text.

## Get the code

[**➡️ View on GitHub: examples/wip/write_tweet.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/wip/write_tweet.py)

## The Pipeline Explained

The `optimize_tweet` function is the core of this example. It takes two strings, `draft_tweet_str` and `writing_style_str`, creates two `Stuff` objects with the concepts `tech_tweet.DraftTweet` and `tech_tweet.WritingStyle`, and then runs the `optimize_tweet_sequence` pipeline.

```python
async def optimize_tweet(draft_tweet_str: str, writing_style_str: str) -> OptimizedTweet:
    # Create the draft tweet stuff
    draft_tweet = StuffFactory.make_stuff(
        concept_str="tech_tweet.DraftTweet",
        content=TextContent(text=draft_tweet_str),
        name="draft_tweet",
    )
    writing_style = StuffFactory.make_stuff(
        concept_str="tech_tweet.WritingStyle",
        content=TextContent(text=writing_style_str),
        name="writing_style",
    )

    # Create working memory
    working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
        [
            draft_tweet,
            writing_style,
        ]
    )

    # Run the sequence pipe
    pipe_output, _ = await execute_pipeline(
        pipe_code="optimize_tweet_sequence",
        working_memory=working_memory,
    )

    # Get the optimized tweet
    optimized_tweet = pipe_output.main_stuff_as(content_type=OptimizedTweet)
    return optimized_tweet
```

This example shows how to use multiple inputs to guide the generation process and produce text that adheres to a specific style. 