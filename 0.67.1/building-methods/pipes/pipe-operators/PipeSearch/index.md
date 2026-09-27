# PipeSearch

The `PipeSearch` operator searches the web using a configurable search provider and returns structured results with an answer and source citations.

## How it works

`PipeSearch` takes a search prompt (which can include `$variable` template references) and sends it to a web search provider (such as Linkup). The provider returns a synthesized answer along with a list of sources.

The output is a `SearchResult` (or a concept that refines it), which contains:

-   `answer`: The synthesized answer text from the search
-   `sources`: A list of sources, each with a `title`, `url`, and optional `snippet`

## Configuration

`PipeSearch` is configured in your pipeline's `.mthds` file.

### Search Models and Backend System

PipeSearch uses the unified inference backend system to manage search providers. This means you can:

- Use different search providers (e.g., Linkup)
- Choose between standard and deep search models, with presets for each
- Route search requests through the same backend system as LLMs and other operators

Common search presets:

- `$standard`: Standard web search with fast results
- `$deep`: Deep web search for more thorough results

### MTHDS Parameters

| Parameter     | Type       | Description                                                                                                                                         | Required |
| ------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `type`        | string     | The type of the pipe: `PipeSearch`                                                                                                                  | Yes      |
| `description` | string     | A description of the search operation.                                                                                                              | Yes      |
| `inputs`      | dictionary | The input concept(s) for the search query, as a dictionary mapping input names to concept codes. Required when the prompt references variables.     | No       |
| `output`      | string     | The output concept produced by the search. `SearchResult` is the default shape, but PipeSearch can also target a structured output concept.         | Yes      |
| `model`       | string     | The search model preset to use (e.g., `"$standard"`, `"$deep"`). Defaults to the model specified in the global config.                | No       |
| `prompt`      | string     | The search query. Can be a static string or reference input variables using `$` prefix (e.g., `"What is $topic?"`).                                 | Yes      |
| `include_images` | boolean | Whether to include images in search results. Overrides the preset setting.                                                                        | No       |
| `max_results`    | integer | Maximum number of results to return. Overrides the preset setting.                                                                                | No       |
| `from_date`      | string  | Start date filter in YYYY-MM-DD format. Only return results from this date onwards.                                                               | No       |
| `to_date`        | string  | End date filter in YYYY-MM-DD format. Only return results up to this date.                                                                        | No       |
| `include_domains` | list of strings | Restrict search to these domains only.                                                                                                    | No       |
| `exclude_domains` | list of strings | Exclude results from these domains.                                                                                                       | No       |

### Example: Static search query

This pipe performs a fixed search query without any inputs.

```toml
[pipe.search_ai_news]
type = "PipeSearch"
description = "Search for the latest AI news"
output = "SearchResult"
model = "$standard"
prompt = "What are the latest developments in artificial intelligence?"
```

### Example: Dynamic search with input variable

This pipe takes a topic as input and searches the web for information about it.

```toml
[pipe.search_topic]
type = "PipeSearch"
description = "Search the web for information about a topic"
inputs = { topic = "Text" }
output = "SearchResult"
model = "$standard"
prompt = "What is $topic?"
```

### Example: Deep search

Use a deep search preset for more thorough results.

```toml
[pipe.deep_research]
type = "PipeSearch"
description = "Perform deep research on a topic"
inputs = { topic = "Text" }
output = "SearchResult"
model = "$deep"
prompt = "What are the main details about $topic?"
```

### Example: Filtering by date and domain

Use date filters and domain restrictions to narrow search results.

```toml
[pipe.search_recent_from_sources]
type = "PipeSearch"
description = "Search specific sources for recent news"
inputs = { topic = "Text" }
output = "SearchResult"
model = "$standard"
prompt = "What are the latest developments about $topic?"
from_date = "2026-01-01"
include_domains = ["reuters.com", "apnews.com", "bbc.com"]
```

When the output concept is compatible with `SearchResult`, the output contains the synthesized `answer` and a list of `sources` with their titles, URLs, and snippets. PipeSearch can also feed a structured output concept when your method needs a more specialized downstream shape.

## Related Documentation

- [Web Search Feature](../../../features/web-search.md) - Overview of web search capabilities
