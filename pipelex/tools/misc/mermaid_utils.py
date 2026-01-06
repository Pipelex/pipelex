"""Mermaid utilities for generating and rendering Mermaid diagrams.

This module provides helper functions for:
- Encoding Mermaid diagrams to shareable URLs
- Sanitizing and escaping strings for Mermaid syntax
- Rendering Mermaid code to standalone HTML pages
"""

import base64
import hashlib
import json
import zlib

from pipelex import pretty_print
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync

# -----------------------------------------------------------------------------
# Encoding utilities for Mermaid URLs
# -----------------------------------------------------------------------------


def encode_pako_encore_from_bytes(state_bytes: bytes) -> str:
    compressed = zlib.compress(state_bytes, level=9)
    serialized_string = base64.urlsafe_b64encode(compressed).decode("utf-8")
    return f"pako:{serialized_string}"


def encode_pako_from_string(state: str) -> str:
    state_bytes = state.encode("utf-8")
    return encode_pako_encore_from_bytes(state_bytes)


def make_mermaid_url(mermaid_code: str) -> str:
    as_dict = {
        "code": mermaid_code,
        "mermaid": {
            "theme": "default",
        },
    }
    encoded = encode_pako_from_string(json.dumps(as_dict))
    return f"https://mermaid.ink/svg/{encoded}"


def print_mermaid_url(url: str, title: str):
    pretty_print("⚠️  Warning: By clicking on the following mermaid URL, you send data to https://mermaid.live/.", border_style="red")
    pretty_print(url, title=title, border_style="yellow")


# -----------------------------------------------------------------------------
# Sanitization and escaping utilities for Mermaid syntax
# -----------------------------------------------------------------------------


def clean_str_for_mermaid_node_title(text: str) -> str:
    """Cleans a string to be safely used as a Mermaid node title by replacing quotes
    with similar Unicode characters that won't interfere with Mermaid syntax.

    Args:
        text: The string to clean

    Returns:
        The cleaned string with quotes replaced

    """
    # Replace single and double quotes with similar Unicode characters
    text = text.replace('"', "″")  # Replace with prime symbol
    return text.replace("'", "′")  # Replace with curly quote


def sanitize_mermaid_id(node_id: str) -> str:
    """Convert a node ID to a valid Mermaid identifier.

    Mermaid IDs cannot contain special characters like ':', '-', '.'.
    We use a hash-based approach to ensure uniqueness and validity.

    Args:
        node_id: The original node ID (may contain special characters).

    Returns:
        A sanitized Mermaid-safe identifier like 'n_abc1234567'.
    """
    # Using sha256 for hashing (only for ID generation, not security)
    hash_digest = hashlib.sha256(node_id.encode()).hexdigest()[:10]
    return f"n_{hash_digest}"


def escape_mermaid_label(label: str) -> str:
    """Escape special characters in Mermaid labels.

    Args:
        label: The label text to escape.

    Returns:
        Escaped label safe for use in Mermaid syntax.
    """
    # Escape quotes and other special characters
    return label.replace('"', "'").replace("[", "(").replace("]", ")")


# -----------------------------------------------------------------------------
# HTML rendering for Mermaid diagrams
# -----------------------------------------------------------------------------


# HTML template for rendering Mermaid diagrams
# The mermaid_code is inserted unescaped since it's plain text for Mermaid parsing
MERMAID_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: var(--bg-color, #f5f5f5);
            transition: background-color 0.3s;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        h1 {
            color: var(--text-color, #333);
            margin: 0;
            transition: color 0.3s;
        }
        .theme-selector {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .theme-selector label {
            font-size: 14px;
            color: var(--label-color, #666);
            transition: color 0.3s;
        }
        .theme-selector select {
            padding: 6px 12px;
            border-radius: 6px;
            border: 1px solid var(--border-color, #ccc);
            background: var(--select-bg, white);
            color: var(--text-color, #333);
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .theme-selector select:hover {
            border-color: var(--border-hover, #999);
        }
        .mermaid-container {
            background-color: var(--container-bg, white);
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            transition: background-color 0.3s;
        }
        .mermaid {
            display: flex;
            justify-content: center;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ title }}</h1>
        <div class="theme-selector">
            <label for="theme-select">Theme:</label>
            <select id="theme-select">
                <option value="default">Default</option>
                <option value="dark">Dark</option>
                <option value="forest">Forest</option>
                <option value="neutral">Neutral</option>
                <option value="base">Base</option>
            </select>
        </div>
    </div>
    <div class="mermaid-container">
        <div class="mermaid" id="mermaid-diagram">
{{ mermaid_code }}
        </div>
    </div>
    <script>
        const mermaidCode = `{{ mermaid_code | replace('`', '\\`') | replace('${', '\\${') }}`;
        let currentTheme = '{{ theme }}';

        // Theme-specific color palettes for custom node styling
        const themePalettes = {
            default: {
                page: { bg: '#f8fafc', text: '#1e293b', label: '#64748b', border: '#cbd5e1',
                        borderHover: '#94a3b8', selectBg: 'white', containerBg: 'white' },
                failed: { fill: '#fee2e2', stroke: '#dc2626' },
                controller: { fill: '#dbeafe', stroke: '#2563eb' },
                pipe: { fill: '#dbeafe', stroke: '#2563eb' },
                stuff: { fill: '#fef3c7', stroke: '#d97706' },
                subgraph: ['#eff6ff', '#ecfdf5', '#fefce8', '#fdf4ff', '#f0fdfa']
            },
            dark: {
                page: { bg: '#1a1a2e', text: '#e0f7fa', label: '#80deea', border: '#2d4a5a',
                        borderHover: '#00bcd4', selectBg: '#2d4a5a', containerBg: '#16213e' },
                failed: { fill: '#3a1a1a', stroke: '#ff5252' },
                controller: { fill: '#1a3a4a', stroke: '#00e5ff' },
                pipe: { fill: '#1a3a4a', stroke: '#00e5ff' },
                stuff: { fill: '#2a1a3a', stroke: '#ff4081' },
                subgraph: ['#1e3a4a', '#1a3a3a', '#2a3a4a', '#1a2a4a', '#2a4a4a']
            },
            forest: {
                page: { bg: '#f0fdf4', text: '#14532d', label: '#166534', border: '#86efac',
                        borderHover: '#4ade80', selectBg: 'white', containerBg: '#fafffe' },
                failed: { fill: '#fecaca', stroke: '#b91c1c' },
                controller: { fill: '#dcfce7', stroke: '#16a34a' },
                pipe: { fill: '#dcfce7', stroke: '#16a34a' },
                stuff: { fill: '#fef9c3', stroke: '#ca8a04' },
                subgraph: ['#d1fae5', '#bbf7d0', '#d9f99d', '#fef08a', '#a7f3d0']
            },
            neutral: {
                page: { bg: '#fafafa', text: '#171717', label: '#525252', border: '#d4d4d4',
                        borderHover: '#a3a3a3', selectBg: 'white', containerBg: 'white' },
                failed: { fill: '#fecaca', stroke: '#991b1b' },
                controller: { fill: '#e5e5e5', stroke: '#525252' },
                pipe: { fill: '#e5e5e5', stroke: '#525252' },
                stuff: { fill: '#fef3c7', stroke: '#92400e' },
                subgraph: ['#f5f5f5', '#e5e5e5', '#fafaf9', '#f5f5f4', '#fafafa']
            },
            base: {
                page: { bg: '#fff', text: '#18181b', label: '#52525b', border: '#e4e4e7',
                        borderHover: '#a1a1aa', selectBg: 'white', containerBg: '#fafafa' },
                failed: { fill: '#ffe4e6', stroke: '#e11d48' },
                controller: { fill: '#e0f2fe', stroke: '#0284c7' },
                pipe: { fill: '#e0f2fe', stroke: '#0284c7' },
                stuff: { fill: '#ffedd5', stroke: '#ea580c' },
                subgraph: ['#f0f9ff', '#f0fdf4', '#fffbeb', '#fdf4ff', '#ecfeff']
            }
        };

        function applyPageTheme(theme) {
            const palette = themePalettes[theme]?.page || themePalettes.default.page;
            document.documentElement.style.setProperty('--bg-color', palette.bg);
            document.documentElement.style.setProperty('--text-color', palette.text);
            document.documentElement.style.setProperty('--label-color', palette.label);
            document.documentElement.style.setProperty('--border-color', palette.border);
            document.documentElement.style.setProperty('--border-hover', palette.borderHover);
            document.documentElement.style.setProperty('--select-bg', palette.selectBg);
            document.documentElement.style.setProperty('--container-bg', palette.containerBg);
        }

        function applyThemeColors(code, theme) {
            const palette = themePalettes[theme] || themePalettes.default;
            let result = code;

            // Replace classDef colors
            result = result.replace(
                /classDef\\s+failed\\s+fill:[^,]+,stroke:[^\\s\\n]+/g,
                `classDef failed fill:${palette.failed.fill},stroke:${palette.failed.stroke}`
            );
            result = result.replace(
                /classDef\\s+controller\\s+fill:[^,]+,stroke:[^\\s\\n]+/g,
                `classDef controller fill:${palette.controller.fill},stroke:${palette.controller.stroke}`
            );
            result = result.replace(
                /classDef\\s+pipe\\s+fill:[^,]+,stroke:[^\\s\\n]+/g,
                `classDef pipe fill:${palette.pipe.fill},stroke:${palette.pipe.stroke}`
            );
            result = result.replace(
                /classDef\\s+pipe_failed\\s+fill:[^,]+,stroke:[^\\s\\n]+/g,
                `classDef pipe_failed fill:${palette.failed.fill},stroke:${palette.failed.stroke}`
            );
            result = result.replace(
                /classDef\\s+stuff\\s+fill:[^,]+,stroke:[^,]+/g,
                `classDef stuff fill:${palette.stuff.fill},stroke:${palette.stuff.stroke}`
            );

            // Replace subgraph fill colors (style sg_xxx fill:#xxx)
            const subgraphColors = palette.subgraph;
            let colorIndex = 0;
            result = result.replace(
                /style\\s+(sg_[^\\s]+)\\s+fill:#[a-fA-F0-9]+/g,
                (match, subgraphId) => {
                    const color = subgraphColors[colorIndex % subgraphColors.length];
                    colorIndex++;
                    return `style ${subgraphId} fill:${color}`;
                }
            );

            return result;
        }

        function initMermaid(theme) {
            mermaid.initialize({
                startOnLoad: false,
                theme: theme,
                flowchart: {
                    useMaxWidth: true,
                    htmlLabels: true,
                    curve: 'basis'
                }
            });
        }

        async function renderDiagram(theme) {
            const container = document.getElementById('mermaid-diagram');
            const themedCode = applyThemeColors(mermaidCode, theme);
            container.innerHTML = themedCode;
            container.removeAttribute('data-processed');
            applyPageTheme(theme);
            initMermaid(theme);
            await mermaid.run({ nodes: [container] });
        }

        // Set initial theme in dropdown
        document.getElementById('theme-select').value = currentTheme;

        // Handle theme change
        document.getElementById('theme-select').addEventListener('change', async (e) => {
            currentTheme = e.target.value;
            await renderDiagram(currentTheme);
        });

        // Initial render on page load
        renderDiagram(currentTheme);
    </script>
</body>
</html>
"""


# Interactive HTML template with clickable stuff nodes that show full data
# Supports multiple formats (JSON, Text, HTML) with runtime toggle
MERMAID_INTERACTIVE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: var(--bg-color, #f5f5f5);
            transition: background-color 0.3s;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        h1 {
            color: var(--text-color, #333);
            margin: 0;
            transition: color 0.3s;
        }
        .theme-selector {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .theme-selector label {
            font-size: 14px;
            color: var(--label-color, #666);
            transition: color 0.3s;
        }
        .theme-selector select {
            padding: 6px 12px;
            border-radius: 6px;
            border: 1px solid var(--border-color, #ccc);
            background: var(--select-bg, white);
            color: var(--text-color, #333);
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .theme-selector select:hover {
            border-color: var(--border-hover, #999);
        }
        .mermaid-container {
            background-color: var(--container-bg, white);
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            transition: background-color 0.3s;
        }
        .mermaid {
            display: flex;
            justify-content: center;
        }
        .hint {
            color: var(--label-color, #666);
            font-size: 14px;
            margin-top: 16px;
            text-align: center;
            transition: color 0.3s;
        }
        .data-modal {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            border-radius: 12px;
            max-width: 80vw;
            max-height: 80vh;
            overflow: auto;
            z-index: 1000;
            display: none;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 13px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            min-width: 400px;
        }
        .data-modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 12px;
            border-bottom: 1px solid #444;
        }
        .data-modal-title {
            font-size: 16px;
            font-weight: 600;
            color: #fff;
        }
        .data-modal-close {
            cursor: pointer;
            color: #888;
            font-size: 24px;
            line-height: 1;
            padding: 4px 8px;
            border-radius: 4px;
            transition: background 0.2s;
        }
        .data-modal-close:hover {
            background: #333;
            color: #fff;
        }
        .format-tabs {
            display: flex;
            gap: 4px;
            margin-bottom: 12px;
        }
        .format-tab {
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            background: #333;
            color: #888;
            border: none;
            transition: all 0.2s;
        }
        .format-tab:hover {
            background: #444;
            color: #ccc;
        }
        .format-tab.active {
            background: #3b82f6;
            color: #fff;
        }
        .format-tab:disabled {
            opacity: 0.4;
            cursor: not-allowed;
        }
        .data-modal-content {
            white-space: pre-wrap;
            word-wrap: break-word;
            line-height: 1.5;
        }
        .data-modal-content.text-content {
            line-height: 0.8;
        }
        .data-modal-content.html-content {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #fff;
            color: #333;
            padding: 12px;
            border-radius: 4px;
        }
        .data-modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 999;
            display: none;
        }
        .clickable-stuff {
            cursor: pointer !important;
        }
        .clickable-stuff:hover {
            filter: brightness(1.1);
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ title }}</h1>
        <div class="theme-selector">
            <label for="theme-select">Theme:</label>
            <select id="theme-select">
                <option value="default">Default</option>
                <option value="dark">Dark</option>
                <option value="forest">Forest</option>
                <option value="neutral">Neutral</option>
                <option value="base">Base</option>
            </select>
        </div>
    </div>
    <div class="mermaid-container">
        <div class="mermaid" id="mermaid-diagram">
{{ mermaid_code }}
        </div>
    </div>
    {% if has_data %}
    <p class="hint">Click on data nodes (orange pills) to view their full content</p>
    {% endif %}
    <div class="data-modal-overlay" id="modal-overlay"></div>
    <div class="data-modal" id="data-modal">
        <div class="data-modal-header">
            <span class="data-modal-title" id="modal-title">Data Content</span>
            <span class="data-modal-close" onclick="hideModal()">&times;</span>
        </div>
        <div class="format-tabs" id="format-tabs">
            <button class="format-tab active" data-format="json" id="tab-json">JSON</button>
            <button class="format-tab" data-format="text" id="tab-text">Pretty</button>
            <button class="format-tab" data-format="html" id="tab-html">HTML</button>
        </div>
        <div class="data-modal-content" id="modal-content"></div>
    </div>
    <script>
        // Embedded stuff data from graph (all formats)
        const stuffDataJson = {{ stuff_data_json }};
        const stuffDataText = {{ stuff_data_text_json }};
        const stuffDataHtml = {{ stuff_data_html_json }};
        const mermaidCode = `{{ mermaid_code | replace('`', '\\`') | replace('${', '\\${') }}`;

        // Track current state
        let currentStuffId = null;
        let currentFormat = 'json';
        let currentTheme = '{{ theme }}';

        // Theme-specific color palettes for custom node styling
        const themePalettes = {
            default: {
                page: { bg: '#f8fafc', text: '#1e293b', label: '#64748b', border: '#cbd5e1',
                        borderHover: '#94a3b8', selectBg: 'white', containerBg: 'white' },
                failed: { fill: '#fee2e2', stroke: '#dc2626' },
                controller: { fill: '#dbeafe', stroke: '#2563eb' },
                pipe: { fill: '#dbeafe', stroke: '#2563eb' },
                stuff: { fill: '#fef3c7', stroke: '#d97706' },
                subgraph: ['#eff6ff', '#ecfdf5', '#fefce8', '#fdf4ff', '#f0fdfa']
            },
            dark: {
                page: { bg: '#1a1a2e', text: '#e0f7fa', label: '#80deea', border: '#2d4a5a',
                        borderHover: '#00bcd4', selectBg: '#2d4a5a', containerBg: '#16213e' },
                failed: { fill: '#3a1a1a', stroke: '#ff5252' },
                controller: { fill: '#1a3a4a', stroke: '#00e5ff' },
                pipe: { fill: '#1a3a4a', stroke: '#00e5ff' },
                stuff: { fill: '#2a1a3a', stroke: '#ff4081' },
                subgraph: ['#1e3a4a', '#1a3a3a', '#2a3a4a', '#1a2a4a', '#2a4a4a']
            },
            forest: {
                page: { bg: '#f0fdf4', text: '#14532d', label: '#166534', border: '#86efac',
                        borderHover: '#4ade80', selectBg: 'white', containerBg: '#fafffe' },
                failed: { fill: '#fecaca', stroke: '#b91c1c' },
                controller: { fill: '#dcfce7', stroke: '#16a34a' },
                pipe: { fill: '#dcfce7', stroke: '#16a34a' },
                stuff: { fill: '#fef9c3', stroke: '#ca8a04' },
                subgraph: ['#d1fae5', '#bbf7d0', '#d9f99d', '#fef08a', '#a7f3d0']
            },
            neutral: {
                page: { bg: '#fafafa', text: '#171717', label: '#525252', border: '#d4d4d4',
                        borderHover: '#a3a3a3', selectBg: 'white', containerBg: 'white' },
                failed: { fill: '#fecaca', stroke: '#991b1b' },
                controller: { fill: '#e5e5e5', stroke: '#525252' },
                pipe: { fill: '#e5e5e5', stroke: '#525252' },
                stuff: { fill: '#fef3c7', stroke: '#92400e' },
                subgraph: ['#f5f5f5', '#e5e5e5', '#fafaf9', '#f5f5f4', '#fafafa']
            },
            base: {
                page: { bg: '#fff', text: '#18181b', label: '#52525b', border: '#e4e4e7',
                        borderHover: '#a1a1aa', selectBg: 'white', containerBg: '#fafafa' },
                failed: { fill: '#ffe4e6', stroke: '#e11d48' },
                controller: { fill: '#e0f2fe', stroke: '#0284c7' },
                pipe: { fill: '#e0f2fe', stroke: '#0284c7' },
                stuff: { fill: '#ffedd5', stroke: '#ea580c' },
                subgraph: ['#f0f9ff', '#f0fdf4', '#fffbeb', '#fdf4ff', '#ecfeff']
            }
        };

        function applyPageTheme(theme) {
            const palette = themePalettes[theme]?.page || themePalettes.default.page;
            document.documentElement.style.setProperty('--bg-color', palette.bg);
            document.documentElement.style.setProperty('--text-color', palette.text);
            document.documentElement.style.setProperty('--label-color', palette.label);
            document.documentElement.style.setProperty('--border-color', palette.border);
            document.documentElement.style.setProperty('--border-hover', palette.borderHover);
            document.documentElement.style.setProperty('--select-bg', palette.selectBg);
            document.documentElement.style.setProperty('--container-bg', palette.containerBg);
        }

        function applyThemeColors(code, theme) {
            const palette = themePalettes[theme] || themePalettes.default;
            let result = code;

            // Replace classDef colors
            result = result.replace(
                /classDef\\s+failed\\s+fill:[^,]+,stroke:[^\\s\\n]+/g,
                `classDef failed fill:${palette.failed.fill},stroke:${palette.failed.stroke}`
            );
            result = result.replace(
                /classDef\\s+controller\\s+fill:[^,]+,stroke:[^\\s\\n]+/g,
                `classDef controller fill:${palette.controller.fill},stroke:${palette.controller.stroke}`
            );
            result = result.replace(
                /classDef\\s+pipe\\s+fill:[^,]+,stroke:[^\\s\\n]+/g,
                `classDef pipe fill:${palette.pipe.fill},stroke:${palette.pipe.stroke}`
            );
            result = result.replace(
                /classDef\\s+pipe_failed\\s+fill:[^,]+,stroke:[^\\s\\n]+/g,
                `classDef pipe_failed fill:${palette.failed.fill},stroke:${palette.failed.stroke}`
            );
            result = result.replace(
                /classDef\\s+stuff\\s+fill:[^,]+,stroke:[^,]+/g,
                `classDef stuff fill:${palette.stuff.fill},stroke:${palette.stuff.stroke}`
            );

            // Replace subgraph fill colors (style sg_xxx fill:#xxx)
            const subgraphColors = palette.subgraph;
            let colorIndex = 0;
            result = result.replace(
                /style\\s+(sg_[^\\s]+)\\s+fill:#[a-fA-F0-9]+/g,
                (match, subgraphId) => {
                    const color = subgraphColors[colorIndex % subgraphColors.length];
                    colorIndex++;
                    return `style ${subgraphId} fill:${color}`;
                }
            );

            return result;
        }

        function initMermaid(theme) {
            mermaid.initialize({
                startOnLoad: false,
                theme: theme,
                flowchart: {
                    useMaxWidth: true,
                    htmlLabels: true,
                    curve: 'basis'
                }
            });
        }

        function attachClickHandlers() {
            // Wait for mermaid to render, then attach click handlers
            setTimeout(() => {
                const svgContainer = document.querySelector('.mermaid svg');
                if (!svgContainer) return;

                // Find nodes by their flowchart IDs - use any available data source
                const allStuffIds = new Set([
                    ...Object.keys(stuffDataJson || {}),
                    ...Object.keys(stuffDataText || {}),
                    ...Object.keys(stuffDataHtml || {})
                ]);

                for (const stuffId of allStuffIds) {
                    // Mermaid generates IDs like 'flowchart-s_xxx-123'
                    const nodes = svgContainer.querySelectorAll(`[id^="flowchart-${stuffId}"]`);
                    nodes.forEach(node => {
                        node.classList.add('clickable-stuff');
                        node.addEventListener('click', (e) => {
                            e.stopPropagation();
                            showModal(stuffId);
                        });
                    });
                }
            }, 500);
        }

        async function renderDiagram(theme) {
            const container = document.getElementById('mermaid-diagram');
            const themedCode = applyThemeColors(mermaidCode, theme);
            container.innerHTML = themedCode;
            container.removeAttribute('data-processed');
            applyPageTheme(theme);
            initMermaid(theme);
            await mermaid.run({ nodes: [container] });
            attachClickHandlers();
        }

        // Set initial theme in dropdown
        document.getElementById('theme-select').value = currentTheme;

        // Handle theme change
        document.getElementById('theme-select').addEventListener('change', async (e) => {
            currentTheme = e.target.value;
            await renderDiagram(currentTheme);
        });

        // Initial render on page load
        renderDiagram(currentTheme);

        // Set up format tab handlers
        document.querySelectorAll('.format-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                if (tab.disabled) return;
                const format = tab.dataset.format;
                setFormat(format);
            });
        });

        function setFormat(format) {
            currentFormat = format;
            // Update tab styling
            document.querySelectorAll('.format-tab').forEach(t => t.classList.remove('active'));
            document.getElementById(`tab-${format}`).classList.add('active');
            // Re-render content if modal is open
            if (currentStuffId) {
                renderContent(currentStuffId, format);
            }
        }

        function renderContent(stuffId, format) {
            const content = document.getElementById('modal-content');
            content.classList.remove('html-content', 'text-content');

            if (format === 'json') {
                const data = stuffDataJson?.[stuffId];
                content.innerHTML = '';
                content.textContent = data ? JSON.stringify(data, null, 2) : 'No JSON data available';
            } else if (format === 'text') {
                const data = stuffDataText?.[stuffId];
                content.classList.add('text-content');
                content.innerHTML = '';
                content.textContent = data || 'No text data available';
            } else if (format === 'html') {
                const data = stuffDataHtml?.[stuffId];
                if (data) {
                    content.classList.add('html-content');
                    content.innerHTML = data;
                } else {
                    content.innerHTML = '';
                    content.textContent = 'No HTML data available';
                }
            }
        }

        function updateTabAvailability(stuffId) {
            const jsonTab = document.getElementById('tab-json');
            const textTab = document.getElementById('tab-text');
            const htmlTab = document.getElementById('tab-html');

            jsonTab.disabled = !stuffDataJson?.[stuffId];
            textTab.disabled = !stuffDataText?.[stuffId];
            htmlTab.disabled = !stuffDataHtml?.[stuffId];

            // Find first available format
            if (!jsonTab.disabled) return 'json';
            if (!textTab.disabled) return 'text';
            if (!htmlTab.disabled) return 'html';
            return 'json';
        }

        function showModal(stuffId) {
            currentStuffId = stuffId;
            const modal = document.getElementById('data-modal');
            const overlay = document.getElementById('modal-overlay');
            const title = document.getElementById('modal-title');

            title.textContent = `Data: ${stuffId}`;

            // Update tab availability and select best format
            const availableFormat = updateTabAvailability(stuffId);

            // If current format is not available, switch to available one
            const currentTab = document.getElementById(`tab-${currentFormat}`);
            if (currentTab.disabled) {
                setFormat(availableFormat);
            } else {
                renderContent(stuffId, currentFormat);
            }

            modal.style.display = 'block';
            overlay.style.display = 'block';
        }

        function hideModal() {
            document.getElementById('data-modal').style.display = 'none';
            document.getElementById('modal-overlay').style.display = 'none';
            currentStuffId = null;
        }

        // Close modal when clicking overlay
        document.getElementById('modal-overlay').addEventListener('click', hideModal);

        // Close modal with Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') hideModal();
        });
    </script>
</body>
</html>
"""


def render_mermaid_html(
    mermaid_code: str,
    *,
    title: str = "Pipelex Graph",
    theme: str = "default",
) -> str:
    """Render Mermaid code into a standalone HTML page (sync version).

    Use this when NOT inside an async event loop. For async contexts,
    use render_mermaid_html_async instead.

    Args:
        mermaid_code: The Mermaid flowchart code to embed.
        title: The page title (appears in browser tab and as h1).
        theme: The Mermaid theme to use (default, base, dark, forest, neutral).

    Returns:
        Complete HTML page as a string.
    """
    return render_jinja2_sync(
        template_source=MERMAID_HTML_TEMPLATE,
        template_category=TemplateCategory.HTML,
        temlating_context={
            "title": title,
            "mermaid_code": mermaid_code,
            "theme": theme,
        },
    )


async def render_mermaid_html_async(
    mermaid_code: str,
    *,
    title: str = "Pipelex Graph",
    theme: str = "default",
) -> str:
    """Render Mermaid code into a standalone HTML page (async version).

    Use this when inside an async event loop.

    Args:
        mermaid_code: The Mermaid flowchart code to embed.
        title: The page title (appears in browser tab and as h1).
        theme: The Mermaid theme to use (default, base, dark, forest, neutral).

    Returns:
        Complete HTML page as a string.
    """
    return await render_jinja2_async(
        template_source=MERMAID_HTML_TEMPLATE,
        template_category=TemplateCategory.HTML,
        temlating_context={
            "title": title,
            "mermaid_code": mermaid_code,
            "theme": theme,
        },
    )


async def render_mermaid_html_with_data_async(
    mermaid_code: str,
    stuff_data: dict[str, str | dict[str, object] | list[str] | list[dict[str, object]] | None] | None = None,
    stuff_data_text: dict[str, str] | None = None,
    stuff_data_html: dict[str, str] | None = None,
    *,
    title: str = "Pipelex Graph",
    theme: str = "default",
) -> str:
    """Render Mermaid code with clickable stuff nodes into a standalone HTML page.

    This renders an interactive version where clicking on stuff nodes (data items)
    displays their full serialized content in a modal dialog. Supports multiple
    display formats (JSON, Text, HTML) with runtime toggle.

    Args:
        mermaid_code: The Mermaid flowchart code to embed.
        stuff_data: Mapping from stuff mermaid IDs to their full data content (JSON format).
        stuff_data_text: Mapping from stuff mermaid IDs to their ASCII text representation.
        stuff_data_html: Mapping from stuff mermaid IDs to their HTML representation.
        title: The page title (appears in browser tab and as h1).
        theme: The Mermaid theme to use (default, base, dark, forest, neutral).

    Returns:
        Complete HTML page as a string with interactive data display.
    """
    has_data = bool(stuff_data or stuff_data_text or stuff_data_html)
    return await render_jinja2_async(
        template_source=MERMAID_INTERACTIVE_HTML_TEMPLATE,
        template_category=TemplateCategory.HTML,
        temlating_context={
            "title": title,
            "mermaid_code": mermaid_code,
            "stuff_data_json": json.dumps(stuff_data or {}),
            "stuff_data_text_json": json.dumps(stuff_data_text or {}),
            "stuff_data_html_json": json.dumps(stuff_data_html or {}),
            "has_data": has_data,
            "theme": theme,
        },
    )
