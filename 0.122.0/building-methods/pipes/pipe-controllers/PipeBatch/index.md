# PipeBatch

The `PipeBatch` controller provides a powerful "map" operation for your pipelines. It takes a list of items as input and runs the same pipe on each item in the list, executing the branches concurrently for efficiency.

This is the ideal controller for processing collections of documents, images, or any other data records where the same logic needs to be applied to each one independently.

## How it works

`PipeBatch` orchestrates a parallel, per-item execution of a single "branch pipe".

1.  **Input List**: It identifies an input list from the working memory.
2.  **Branching**: For each item in the input list, it creates a new, isolated execution branch.
3.  **Isolation & Injection**: Each branch gets its own working memory, holding a copy of its item, under the `input_item_name`, and a copy of each value its branch pipe reads: the pipe's declared inputs, and what its own steps need when it is a controller. The rest of the batch's working memory, the batched list included, is not copied into the branch, so starting a batch costs its number of items plus the size of what a branch reads, never the two multiplied. Because every copy is the branch's own, a branch that rewrites its item or an input in place (a `PipeFunc` can) leaves the batched list, the batch's memory and every other branch as they were. A branch pipe reads only what it declares as inputs: a `PipeFunc` branch looking up a value its pipe does not declare does not find it.
4.  **Concurrent Execution**: The specified `branch_pipe_code` runs across the branches concurrently, by default at most `max_concurrency` branches at a time, the next branch starting as soon as a running one ends. Each branch pipe operates only on its own item.
5.  **Aggregation**: As each branch ends, `PipeBatch` keeps its output and drops the working memory the branch ran in, with the intermediate values its steps produced. After all branches have completed, it aggregates the outputs into a single new list, which becomes the final output of the `PipeBatch` pipe.

## Concurrency

`PipeBatch` does not spawn every branch at once. At most `max_concurrency` branches run at a time, a setting under `[interpreter.pipeline_execution]` (default `8`), and they run as a sliding window: the branches start in the order of the list, and the next one starts as soon as any running branch ends, so one slow item holds up only its own place and never the branches after it. A branch's working memory is made only when it starts, so at most `max_concurrency` branch memories exist at once. This keeps a large batch — one pipe over thousands of items — from overwhelming memory, the asyncio event loop, and provider rate limits.

To restore unbounded fan-out (every branch started at once), set `max_concurrency = "unbounded"`.

The setting is read **once, when the run's parameters are built**, and then frozen onto the run (`PipeRunParams.batch_max_concurrency`) — every `PipeBatch` in that run, at any depth, uses the value that was in effect when the run started. Editing the config while a run is in flight does not reshape it. This matters most on a durable-execution backend, where the bound also decides which branches start at each of the backend's task boundaries: a value re-read mid-run could make a replay start its branches in a different order from the recorded history.

Results always preserve input order regardless of the concurrency bound.

### When a branch fails

When a branch fails, the batch starts no further branch. The branches already running are not cancelled: each runs to its end, so its steps finish cleanly and record their trace and their cost, rather than being cut off in the middle of a model call that is billed either way. Once every running branch has ended, the batch fails with the error of the failed branch that comes first in the list, whichever failed first in time. The branches that had not started never run, and the batch hands back no partial list.

So with a bounded window a failure costs at most the branches that were running beside it, `max_concurrency` minus one at the most, never the rest of the list. Under `max_concurrency = "unbounded"` every branch is already running when one fails, so every one of them runs to its end. On a durable backend, which branches had started when the failure came depends only on the order in which branches ended, which the run's history records, so a replay starts exactly the same branches.

For durable, rate-limited execution of very large batches, run the pipeline on the Temporal track. A live batch over more than 100 items run in process logs a warning saying so; a durable backend whose router runs the batch durably leaves that warning out.

## Very wide batches on a durable runtime

On a durable runtime, a run keeps a history of what it did, and its engine bounds that history in bytes and in events. Every item of a batch writes into its run's history what its branch starts with and what it hands back, so the number of items a batch can run depends on how large each item and its branch's inputs are, not on a fixed item count.

Before its first item starts, a `PipeBatch` asks the runtime's router whether the whole batch fits. A runtime that runs in one process keeps no such history and always answers yes. A durable runtime may estimate what the batch would write from its first item and its item count, and refuse a batch that would not fit, before any item is billed, rather than let its engine end the run halfway; a runtime that does not check lets the batch run. A refused batch fails at the `PipeBatch` with `input.too_large`, whose `input` is the batched list as you named it, whose `size` is its item count and whose `limit` is the largest item count that fits, left out when not even one item fits; its message, for the operator, also names the bytes and the events the batch would write and those the run had left. When items later in the list turn out much larger than the first, the runtime may also stop the batch during its fan-out, with the same code and a message saying how many items had started.

To run a list that is refused, split it into shorter lists, each batched by a run of its own, or make each item, and what its branch pipe reads besides it, smaller. When not even one item fits, only smaller items help, and the refusal says so.

## Compaction Under Absence

When a branch's result resolves as a recorded absence — typically because the branch pipe is a `PipeCondition` whose outcome was `continue`, or the branch was skipped (lifted) on an absent optional value — that branch contributes **no item** to the aggregated output list. The list is compacted: a list cannot hold a hole, and absent results are dropped rather than replaced by placeholders. Order is preserved among the results that did produce a value, and each dropped branch is logged at `DEBUG`, with its index among the inputs and its absence reason as the fields `branch_index` and `absence_reason`, which is how a log explains an output list shorter than its input.

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
| `input_list_name`  | string       | The name of the input list to iterate over. Must match one of the keys in `inputs`, so it is a plain input name, a `snake_case` identifier matching `[a-z][a-z0-9_]*`, and never a path into a field: a dotted name such as `catalog.pages` is refused as `invalid_input_name`. To map a pipe over a list held in a field, have the calling sequence bind it to the batch's list with a binding step, or run the branch pipe in a sequence step whose dotted `batch_over` binds the list and batches over it (see [Batching over a field](PipeSequence.md#batching-over-a-field)). Typically a plural noun (e.g. `articles`). | Yes      |
| `input_item_name`  | string       | The name that an individual item from the list will have inside its execution branch — this is how the branch pipe finds its input. It is a [stored name](PipeSequence.md#stored-names), so a plain input name like `input_list_name`, a `snake_case` identifier matching `[a-z][a-z0-9_]*`: a name in any other form, such as `Article`, `issue.article` or `_bound_article`, is refused as `invalid_input_name`. Must differ from `input_list_name` and from every key in `inputs`. Typically the singular form of the list name (e.g. `article`). | Yes      |

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
5.  Steps 3 and 4 run concurrently across branches, up to `max_concurrency` at a time (8 by default): articles 1 to 8 start together, and article 9 starts as soon as any of them is summarized, until all 10 articles are processed.
6.  Once all `summarize_one_article` pipes are done, `PipeBatch` collects the 10 `ArticleSummary` outputs and bundles them into a single `ArticleSummary[]` list. This list is the final result.

## Related Documentation

- [Understanding Multiplicity](../understanding-multiplicity.md) - How Pipelex handles lists and batch processing
- [Understanding Optionality](../understanding-optionality.md) - Presence markers, absence records, and compaction
