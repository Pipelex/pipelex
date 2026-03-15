---
title: "Tweet Optimizer Example"
description: "Optimize tech tweets with style transfer using Pipelex — analyze for pitfalls then rewrite based on a reference writing style."
---

# Example: Tweet Optimizer

!!! warning "Work in Progress"
    This example is under active development and may change.

This example takes a draft tweet and a reference writing style, then optimizes the tweet through a two-step "analyze and optimize" pipeline. The analysis step checks for common pitfalls (fluffiness, cringiness, humblebragginess, vagueness), and the optimization step rewrites the tweet based on that analysis.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/wip/write_tweet/tech_tweet.mthds)

## What it demonstrates

- Two-step "analyze then refine" pattern
- Multiple inputs (`DraftTweet`, `WritingStyle`) flowing into a `PipeSequence`
- Specialized model references (`$writing-factual`, `$writing-creative`)
- Simple concept definitions without structures (text-only concepts)

## The Method: `tech_tweet.mthds`

### Concepts

```toml
domain      = "tech_tweet"
main_pipe   = "optimize_tweet_sequence"

[concept]
DraftTweet     = "A draft version of a tech tweet that needs optimization"
OptimizedTweet = "A tweet optimized for Twitter/X engagement following best practices"
TweetAnalysis  = "Analysis of the tweet's structure and potential improvements"
WritingStyle   = "A style of writing"
```

### Pipeline

```toml
[pipe.optimize_tweet_sequence]
type = "PipeSequence"
description = "Analyze and optimize a tech tweet in sequence"
inputs = { draft_tweet = "DraftTweet", writing_style = "WritingStyle" }
output = "OptimizedTweet"
steps = [
  { pipe = "analyze_tweet", result = "tweet_analysis" },
  { pipe = "optimize_tweet", result = "optimized_tweet" },
]
```

The analysis pipe evaluates the tweet for fluffiness, cringiness, humblebragginess, and vagueness — scoring each 1-5. The optimization pipe then rewrites based on this analysis and the reference writing style.

## How to run

```bash
pipelex run bundle examples/wip/write_tweet/tech_tweet.mthds \
  -i examples/wip/write_tweet/inputs.json
```

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
