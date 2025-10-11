# Tracker Configuration

The Tracker Configuration allows you to customize how your pipeline execution is tracked and visualized. The tracker creates a Mermaid flowchart visualization of your pipeline's execution, showing how data flows through different pipes and transformations.

## Overview

The pipeline tracker visualizes:

- Stuff nodes (data objects) and their transformations
- Pipe execution steps
- Batch processing branches
- Condition nodes and choices
- Aggregation steps

## Configuration Options

### Basic Settings

- `is_debug_mode` (bool): Enable or disable debug mode for tracking
    - When enabled, shows additional information like:
        - Node codes and internal identifiers
        - Extended comments for repeated nodes
        - Pipe codes in edge captions with comments

- `is_include_text_preview` (bool): Whether to include text previews in the tracking interface
    - When enabled, shows first 100 characters of text content in stuff nodes
    - Only applies to text-based stuff objects

- `is_include_interactivity` (bool): Enable or disable interactive features in the tracking interface

### Visual Settings

- `theme` (str | "auto"): The visual theme to use for the Mermaid flowchart

    - Use "auto" for automatic theme selection based on context
    - Or specify a custom theme name

- `layout` (str | "auto"): The layout algorithm to use for graph visualization

    - Use "auto" for automatic layout selection
    - Or specify a custom layout algorithm
    - Affects how nodes and edges are arranged in the flowchart

- `wrapping_width` (int | "auto"): Text wrapping width for node labels

    - Use "auto" for automatic width adjustment
    - Or specify a fixed width in characters
    - Helps control the visual width of node content

- `nb_items_limit` (int | "unlimited"): Maximum number of items to display

    - Use "unlimited" for no limit
    - Or specify a maximum number of items
    - Helps manage visualization of large pipelines

### Graph Styling

- `sub_graph_colors` (List[str]): List of colors to use for sub-graphs

  - Colors are used to visually distinguish different pipeline layers
  - Example: `["#1f77b4", "#ff7f0e", "#2ca02c"]`

- Edge Styles (all str type):

  - `pipe_edge_style`: Style for regular pipe transformation edges
  - `branch_edge_style`: Style for batch processing branch edges
  - `aggregate_edge_style`: Style for aggregation step edges
  - `condition_edge_style`: Style for condition evaluation edges
  - `choice_edge_style`: Style for condition choice result edges

## Example Configuration

```toml
[tracker]
is_debug_mode = false
is_include_text_preview = false
is_include_interactivity = false
theme = "base"
layout = "dagre"
wrapping_width = "auto"
nb_items_limit = "unlimited"
sub_graph_colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]
pipe_edge_style = "---->"
branch_edge_style = "-...-"
aggregate_edge_style = "-...-"
condition_edge_style = "-----"
choice_edge_style = "-----"
```

## Property Accessors

The TrackerConfig class provides convenient property accessors that handle the "auto" and "unlimited" special values:

- `applied_theme`: Returns None for "auto", otherwise returns the theme name
- `applied_layout`: Returns None for "auto", otherwise returns the layout name
- `applied_wrapping_width`: Returns None for "auto", otherwise returns the width as an integer
- `applied_nb_items_limit`: Returns None for "unlimited", otherwise returns the limit as an integer

These properties make it easy to work with the configuration values in your code while maintaining the flexibility of automatic settings.

## Visualization Features

The tracker generates Mermaid flowcharts with the following features:

1. Node Types:

    - Start node (special)
    - Stuff nodes (data objects)
    - Condition nodes (for pipeline branching)

2. Edge Types:

    - Pipe edges (regular transformations)
    - Branch edges (batch processing)
    - Aggregate edges (combining results)
    - Condition edges (with expressions)
    - Choice edges (condition results)

3. Node Content:

    - Concept type and name
    - Content preview (for text)
    - Debug information (when debug mode is enabled)
    - Comments and descriptions

4. Visual Organization:

    - Sub-graphs for different pipeline layers
    - Color coding for visual distinction
    - Different edge styles for different types of connections
