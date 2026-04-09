# TODOs

## Graph viewer: use relative URLs for storage assets

**What:** When generating graph HTML output, copy referenced storage files (images, PDFs) into an `assets/` subdirectory next to the HTML file and set `public_url` to relative paths (`assets/filename.ext`) instead of `file://` absolute paths.

**Why:** `file://` URLs are blocked by browsers when the HTML is served over HTTP (e.g., `localhost:3002`). Images and PDFs don't render in the graph viewer panel. Relative URLs work in all contexts: opened as a local file, served over HTTP, zipped and shared, or deployed to cloud.

**Where to start:**
- `pipelex/tools/storage/local_storage_provider.py:108-119` — where `file://` URLs are generated via `file_path.as_uri()`
- `pipelex/graph/graph_rendering.py` — where graph HTML is generated. This is where file copying should happen.
- `pipelex/pipeline/input_normalizer.py:182-239` — where `public_url` is populated on ImageContent/DocumentContent
- S3/GCP providers already generate absolute HTTPS URLs and need no changes

**Approach:** During graph HTML generation, resolve all `pipelex-storage://` URIs to local file paths, copy them into an `assets/` subdirectory next to the output HTML, and rewrite `public_url` to the relative path. This follows the pattern used by pytest-html, Allure reports, and static site generators.

**Depends on:** Nothing. Self-contained change in pipelex.
