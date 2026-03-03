# PipeSearch

The `PipeSearch` operator searches the web using a configurable search provider and returns structured results with an answer and source citations.

## How it works

`PipeSearch` takes a search prompt (which can include `$variable` template references) and sends it to a web search provider (such as Linkup). The provider returns a synthesized answer along with a list of sources.

The output is a `SearchResult` (or a concept that refines it), which contains:

-   `answer`: The synthesized answer text from the search
-   `sources`: A list of sources, each with a `name`, `url`, and optional `snippet`

## Configuration

`PipeSearch` is configured in your pipeline's `.mthds` file.

### Search Models and Backend System

PipeSearch uses the unified inference backend system to manage search providers. This means you can:

- Use different search providers (e.g., Linkup)
- Configure search depth (standard vs deep) through presets
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
| `output`      | string     | The output concept produced by the search. Must be `SearchResult` or a concept that refines `SearchResult`.                                         | Yes      |
| `model`       | string     | The search model preset to use (e.g., `"$standard"`, `"$deep"`). Defaults to the model specified in the global config.                | No       |
| `prompt`      | string     | The search query. Can be a static string or reference input variables using `$` prefix (e.g., `"What is $topic?"`).                                 | Yes      |

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

The output of PipeSearch must be `SearchResult` or a concept that refines `SearchResult`. After execution, the output contains the synthesized `answer` and a list of `sources` with their names, URLs, and snippets.
