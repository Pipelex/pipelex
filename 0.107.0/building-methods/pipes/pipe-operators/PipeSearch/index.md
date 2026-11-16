# PipeSearch

The `PipeSearch` operator searches the web using a configurable search provider and returns structured results with an answer and source citations.

## How it works

`PipeSearch` takes a search prompt (which can include `$variable` template references) and sends it to a web search provider (such as Linkup). The provider returns a synthesized answer along with a list of sources.

The output is a `SearchResult` (or a concept that refines it), which contains:

-   `answer`: The synthesized answer text from the search
-   `sources`: A list of sources, each with a `title`, `url`, and optional `snippet`

Each source is listed once. When the provider lists the same page more than once, the first entry is kept with its original address, the order of the provider's list is kept, and the other entries are dropped. Two sources name the same page when their addresses are equal after these steps:

-   `http` and `https` count as the same scheme.
-   The host is lowercased, and one leading `www.` is dropped.
-   The fragment (`#section`) is dropped.
-   One trailing `/` is dropped from the path, unless the path is `/` alone. An address written with no path, such as `https://example.com`, has the path `/`.
-   The query (`?page=2`) is kept as it is.

So `https://www.example.com/guide/` and `http://example.com/guide#intro` name the same page, while `https://example.com/guide` and `https://example.com/docs/guide` are two pages.

The answer cites its sources inline as `[1]`, `[2][3]`, and so on, numbered from 1 in the order of the provider's list. Each citation is renumbered to the position its source holds in the shortened list, so it still points at the source it named, and a citation of a dropped entry points at the entry kept for its page. A number that names no source is left as written, and so are numbers inside code spans and code blocks, as CommonMark reads them:

-   A code block is fenced with backticks or tildes, or indented, and it is code wherever it stands, inside block quotes and lists included.
-   A code span opens on a run of backticks and closes on the next run of the same length. It never runs past the paragraph, heading, list item or table cell it opens in, and a backtick escaped with a backslash (`` \` ``) opens none.

Every input the pipe declares must be read by the `prompt`, and every variable the prompt reads must be declared in `inputs`. Validation refuses an input the prompt never reads as `extraneous_input_variable`, naming the input, so you either reference it in the prompt or remove it from `inputs`; an undeclared variable is refused as `missing_input_variable`.

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
