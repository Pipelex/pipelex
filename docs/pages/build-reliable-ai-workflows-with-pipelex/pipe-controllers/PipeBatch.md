# PipeBatch

The `PipeBatch` controller provides a powerful "map" operation for your pipelines. It takes a list of items as input and runs the same pipe on each item in the list, executing them all in parallel for maximum efficiency.

This is the ideal controller for processing collections of documents, images, or any other data records where the same logic needs to be applied to each one independently.

## How it works

`PipeBatch` orchestrates a parallel, per-item execution of a single "branch pipe".

1.  **Input List**: It identifies an input list from the working memory.
2.  **Branching**: For each item in the input list, it creates a new, isolated execution branch.
3.  **Isolation & Injection**: Each branch gets a deep copy of the `WorkingMemory`. The specific item for that branch is injected into this memory with a defined name.
4.  **Concurrent Execution**: The specified `branch_pipe_code` is executed in all branches simultaneously. Each branch pipe operates only on its own item.
5.  **Aggregation**: After all branches have completed, `PipeBatch` collects the individual output from each one and aggregates them into a single new list. This list becomes the final output of the `PipeBatch` pipe.

## Configuration

`PipeBatch` is configured in your pipeline's `.plx` file.

### PLX Parameters

| Parameter          | Type         | Description                                                                                                                                      | Required |
| ------------------ | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| `type`             | string       | The type of the pipe: `PipeBatch`                                                                          | Yes      |
| `definition`      | string       | A description of the batch operation.                                                                           | Yes      |
| `inputs`           | dictionary   | The input concept(s) for the batch operation, as a dictionary mapping input names to concept codes.                                                     | Yes       |
| `output`           | string       | The output concept produced by the batch operation.                                                | Yes      |
| `branch_pipe_code` | string       | The name of the single pipe to execute for each item in the input list.                                                                          | Yes      |
| `batch_params`     | table (dict) | An optional table to provide more specific names for the batch operation.                                                                        | No       |

### Batch Parameters (`batch_params`)

| Key                     | Type   | Description                                                                                                                           | Required |
| ----------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `input_list_stuff_name` | string | The name of the list in the `WorkingMemory` to iterate over. If not provided, it defaults to the name of the `PipeBatch`'s main `input`. | No       |
| `input_item_stuff_name` | string | The name that an individual item from the list will have inside its execution branch. This is how the branch pipe finds its input.   | Yes      |

### Example: Summarizing a list of articles

Suppose you have a list of articles and you want to generate a summary for each one.

```plx
# The pipe that knows how to summarize one article
[pipe.summarize_one_article]
type = "PipeLLM"
definition = "Summarize a single article"
inputs = { article = "ArticleText" }
output = "ArticleSummary"
prompt_template = "Please provide a one-sentence summary of the following article:\n\n@article_text"

# The PipeBatch definition
[pipe.summarize_all_articles]
type = "PipeBatch"
definition = "Summarize a batch of articles in parallel"
inputs = { articles = "ArticleList" }  # This is the list to iterate over
output = "SummaryList" # This will be the list of summaries
branch_pipe_code = "summarize_one_article"

input_item_name = "ArticleText" # Name of an item within the branch
```

How this works:
1.  The `summarize_all_articles` pipe receives an `ArticleList`. Let's say it contains 10 articles.
2.  `PipeBatch` creates 10 parallel branches.
3.  In branch #1, it takes the first article from `ArticleList`, puts it into the branch's isolated working memory, and gives it the name `ArticleText` (as specified by `input_item_name`).
4.  The `summarize_one_article` pipe is then executed in branch #1. It looks for an input named `ArticleText`, finds the injected article, and produces a summary.
5.  Steps 3 and 4 happen simultaneously for all 10 articles in their respective branches.
6.  Once all `summarize_one_article` pipes are done, `PipeBatch` collects the 10 `ArticleSummary` outputs and bundles them into a single `SummaryList`. This list is the final result. 