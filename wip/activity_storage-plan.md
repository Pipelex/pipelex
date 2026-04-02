# Activity-Level Storage — Execution Plan

> Design: [wip/activity_storage.md](wip/activity_storage.md)
> Branch: `fix/Temporal-Img`

---

## Phase 1: Image Generation (fixes the immediate bug) ✅

### 1.1 Modify `act_img_gen_images` to include storage

- [x] **File**: `pipelex/cogt/content_generation/img_gen_generate.py`
  - Add `img_gen_single_image_and_store()` and `img_gen_image_list_and_store()` functions
  - These call the existing generation logic, then use `GeneratedContentFactory` (with `get_storage_provider()`) to store and return `ImageContent`
  - Keep the original `img_gen_single_image()` and `img_gen_image_list()` functions for the non-Temporal path

- [x] **File**: `pipelex/temporal/tprl_content_generation/act_img_gen_generate.py`
  - Change `act_img_gen_images` return type: `list[GeneratedImageRawDetails]` → `list[ImageContent]`
  - Call the new `_and_store` functions instead of the raw generation functions
  - The activity receives `ImgGenAssignment` (unchanged) which already has `job_metadata` with `user_id` and `pipeline_run_id`

### 1.2 Update `WfMakeImages`

- [x] **File**: `pipelex/temporal/tprl_content_generation/wf_make_images.py`
  - Change return type: `list[GeneratedImageRawDetails]` → `list[ImageContent]`
  - No logic changes — just the type annotation

### 1.3 Update `ContentGeneratorChild` and `ContentGeneratorTop`

- [x] **File**: `pipelex/temporal/tprl_content_generation/content_generator_child.py`
  - `make_single_image()`: Gets `list[ImageContent]` from `WfMakeImages`, extracts the single item directly. Removed `make_image_content()` call
  - `make_image_list()`: Gets `list[ImageContent]` from `WfMakeImages`, returns directly. Removed comprehension calling `make_image_content()`
  - `make_image_content()`: Kept for protocol compliance but no longer called from image generation paths

- [x] **File**: `pipelex/temporal/tprl_content_generation/content_generator_top.py`
  - Same changes as `ContentGeneratorChild` — `make_single_image()` and `make_image_list()` now use `ImageContent` directly from workflow

### 1.4 Update test workflow

- [x] **File**: `pipelex/temporal/test_extras/wf_test_content_generator_child.py`
  - Image generation is commented out (pre-existing TODO). No changes needed

### 1.5 Lint + test

- [x] Run `make agent-check` — 0 errors, 0 warnings
- [x] Run `make agent-test` — all tests passed

---

## Phase 2: Extraction with images ✅

### 2.1 Modify `act_extract_gen_extract_pages` to include storage

- [x] **File**: `pipelex/cogt/content_generation/extract_generate.py`
  - Added `extract_gen_pages_and_store()` that calls extraction, then uses `GeneratedContentFactory.make_page_contents()` to store extracted images and return `list[PageContent]`
  - Kept original `extract_gen_pages()` for non-Temporal path

- [x] **File**: `pipelex/temporal/tprl_content_generation/act_extract_generate.py`
  - Changed return type: `ExtractOutput` → `list[PageContent]`
  - Calls the new `_and_store` function

### 2.2 Update `WfMakeExtract`

- [x] **File**: `pipelex/temporal/tprl_content_generation/wf_make_extract.py`
  - Changed return type: `ExtractOutput` → `list[PageContent]`

### 2.3 Update `ContentGeneratorChild.make_extract_pages` and `ContentGeneratorTop`

- [x] **File**: `pipelex/temporal/tprl_content_generation/content_generator_child.py`
  - `make_extract_pages()`: Gets `list[PageContent]` from `WfMakeExtract`, returns directly. Removed `make_page_contents()` call

- [x] **File**: `pipelex/temporal/tprl_content_generation/content_generator_top.py`
  - Same changes as `ContentGeneratorChild`

### 2.4 Lint + test

- [x] Run `make agent-check` — 0 errors, 0 warnings
- [x] Run `make agent-test` — all tests passed

---

## Phase 3: Page view rendering ✅

### 3.1 Create new activity and workflow for page view rendering

- [x] **File**: `pipelex/cogt/content_generation/assignment_models.py`
  - Added `RenderPageViewsAssignment` model with `job_metadata`, `document_uri`, `page_views_dpi`

- [x] **File** (new): `pipelex/temporal/tprl_content_generation/act_render_page_views.py`
  - Created `act_render_page_views` activity
  - Renders PDF pages via pypdfium2, stores images, returns `list[ImageContent]`

- [x] **File** (new): `pipelex/temporal/tprl_content_generation/wf_render_page_views.py`
  - Created `WfRenderPageViews` workflow wrapping the activity

### 3.2 Update `ContentGeneratorChild.make_render_page_views` and `ContentGeneratorTop`

- [x] **File**: `pipelex/temporal/tprl_content_generation/content_generator_child.py`
  - `make_render_page_views()`: Delegates to `WfRenderPageViews` child workflow. Removed direct pypdfium2 rendering and `make_image_content` calls

- [x] **File**: `pipelex/temporal/tprl_content_generation/content_generator_top.py`
  - Same changes — delegates to `WfRenderPageViews` workflow

### 3.3 Register in task catalog

- [x] **File**: `pipelex/temporal/tasks.py`
  - Added `WfRenderPageViews` to `CRAFTING` workflow list
  - Added `act_render_page_views` to `CRAFTING` activity list

### 3.4 Lint + test

- [x] Run `make agent-check` — 0 errors, 0 warnings (ruff auto-removed unused imports)
- [x] Run `make agent-test` — all tests passed

---

## Phase 4: Cleanup and full validation ✅

- [x] Run `make agent-check` (full lint + type check) — 0 errors
- [x] Run `make agent-test` (full test suite) — all passed
- [ ] Verify no `PayloadSizeWarning` in worker logs (requires live Temporal test)
- [ ] Verify no `NotImplementedError` crashes (requires live Temporal test)
- [ ] Run `/temporal-e2e-validate` Mode 2 (3-process test) — includes image payload tiers
