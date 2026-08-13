---
description: "PipeBatch maps a single pipe over a list of items in parallel. Process collections of documents or records efficiently in Pipelex pipelines."
---

# PipeBatch

The `PipeBatch` controller provides a powerful "map" operation for your pipelines. It takes a list of items as input and runs the same pipe on each item in the list, executing the branches concurrently for efficiency.

This is the ideal controller for processing collections of documents, images, or any other data records where the same logic needs to be applied to each one independently.

## How it works

`PipeBatch` orchestrates a parallel, per-item execution of a single "branch pipe".

1.  **Input List**: It identifies an input list from the working memory.
2.  **Branching**: For each item in the input list, it creates a new, isolated execution branch.
3.  **Isolation & Injection**: Each branch gets a deep copy of the `WorkingMemory`. The specific item for that branch is injected into this memory with a defined name.
4.  **Concurrent Execution**: The specified `branch_pipe_code` runs across the branches concurrently — in bounded chunks, by default at most `max_concurrency` branches at a time. Each branch pipe operates only on its own item.
5.  **Aggregation**: After all branches have completed, `PipeBatch` collects the individual output from each one and aggregates them into a single new list. This list becomes the final output of the `PipeBatch` pipe.

## Concurrency

`PipeBatch` does not spawn every branch at once. Branches run in bounded concurrent chunks, capped by the `max_concurrency` setting under `[pipelex.pipeline_execution_config]` (default `8`). This keeps a large batch — one pipe over thousands of items — from overwhelming memory, the asyncio event loop, and provider rate limits.

To restore unbounded fan-out (every branch started at once), set `max_concurrency = "unbounded"`.

The setting is read **once, when the run's parameters are built**, and then frozen onto the run (`PipeRunParams.batch_max_concurrency`) — every `PipeBatch` in that run, at any depth, uses the value that was in effect when the run started. Editing the config while a run is in flight does not reshape it. This matters most on a durable-execution backend, where the bound is also the chunk size that decides where the backend's task boundaries fall between branch dispatches: a value re-read mid-run could make a replay group its dispatches differently from the recorded history.

Results always preserve input order regardless of the concurrency bound. If a branch fails, the failure propagates and the first error by input index wins.

For durable, rate-limited execution of very large batches, run the pipeline on the Temporal track.

## Compaction Under Absence

When a branch's result resolves as a recorded absence — typically because the branch pipe is a `PipeCondition` whose outcome was `continue`, or the branch was skipped (lifted) on an absent optional value — that branch contributes **no item** to the aggregated output list. The list is compacted: a list cannot hold a hole, and absent results are dropped rather than replaced by placeholders. Order is preserved among the results that did produce a value, and each dropped branch is logged with its absence reason.

This is the batch arm of the "route or skip" pattern: batch over items with a condition branch pipe that builds a result for the items that qualify and `continue`s past the rest — the output is the compacted list of qualifying results. See [Understanding Optionality](../understanding-optionality.md) for the full absence model.

## Configuration

`PipeBatch` is configured in your pipeline's `.mthds` file.

### MTHDS Parameters

| Parameter          | Type         | Description                                                                                                                                      | Required |
| ------------------ | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| `type`             | string       | The type of the pipe: `PipeBatch`                                                                          | Yes      |
| `description`      | string       | A description of the batch operation.                                                                           | Yes      |
| `inputs`           | dictionary   | The input concept(s) for the batch operation, as a dictionary mapping input names to concept codes.                                                     | Yes       |
| `output`           | string       | The output concept produced by the batch operation.                                                | Yes      |
| `branch_pipe_code` | string       | The name of the single pipe to execute for each item in the input list.                                                                          | Yes      |
| `input_list_name`  | string       | The name of the input list to iterate over. Must match one of the keys in `inputs`. Typically a plural noun (e.g. `articles`).                   | Yes      |
| `input_item_name`  | string       | The name that an individual item from the list will have inside its execution branch — this is how the branch pipe finds its input. Must differ from `input_list_name` and from every key in `inputs`. Typically the singular form of the list name (e.g. `article`). | Yes      |

### Example: Summarizing a list of articles

Suppose you have a list of articles and you want to generate a summary for each one.

```toml
# The pipe that knows how to summarize one article
[pipe.summarize_one_article]
type = "PipeLLM"
description = "Summarize a single article"
inputs = { article = "ArticleText" }
output = "ArticleSummary"
prompt = "Please provide a one-sentence summary of the following article:\n\n@article"

# The PipeBatch definition
[pipe.summarize_all_articles]
type = "PipeBatch"
description = "Summarize a batch of articles in parallel"
inputs = { articles = "ArticleText[]" }  # This is the list to iterate over
output = "ArticleSummary[]" # This will be the list of summaries
branch_pipe_code = "summarize_one_article"
input_list_name = "articles" # Name of the input list to iterate over
input_item_name = "article" # Name of an item within the branch
```

How this works:
1.  The `summarize_all_articles` pipe receives a list of `ArticleText` items under the name `articles`. Let's say it contains 10 articles.
2.  `PipeBatch` creates 10 parallel branches.
3.  In branch #1, it takes the first article from the `articles` list, puts it into the branch's isolated working memory, and gives it the name `article` (as specified by `input_item_name`).
4.  The `summarize_one_article` pipe is then executed in branch #1. It looks for an input named `article`, finds the injected article, and produces a summary.
5.  Steps 3 and 4 run concurrently across branches, up to `max_concurrency` at a time (8 by default), until all 10 articles are processed.
6.  Once all `summarize_one_article` pipes are done, `PipeBatch` collects the 10 `ArticleSummary` outputs and bundles them into a single `ArticleSummary[]` list. This list is the final result.

## Related Documentation

- [Understanding Multiplicity](../understanding-multiplicity.md) - How Pipelex handles lists and batch processing
- [Understanding Optionality](../understanding-optionality.md) - Presence markers, absence records, and compaction
