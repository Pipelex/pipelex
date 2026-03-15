# Documentation Site Architecture

This file documents non-obvious architectural decisions for the docs site (`docs.pipelex.com`). Read this before modifying anything under `docs/`.

## Site Architecture Overview

- MkDocs Material with `mike` versioning, published at `docs.pipelex.com`
- `site_url` is `https://docs.pipelex.com/latest/` — all canonical URLs include `/latest/`
- Custom domain via `docs/CNAME` (value: `docs.pipelex.com`)
- Theme overrides live in `docs/overrides/`

## URL Structure & Redirects

Legacy URL paths (e.g. `home/1-features/`) are redirected to current clean paths (e.g. `features/`) via two mechanisms:

- The `mkdocs-redirects` plugin maps old→new paths (see `redirect_maps` in `mkdocs.yml`)
- `docs/404.html` contains client-side JS rewrite rules for the same prefixes, covering URLs that bypass MkDocs routing

Both must stay in sync. `mkdocs-redirects` must be installed in CI (`doc-check.yml`).

## The Two 404 Pages (critical — do not conflate)

There are two distinct 404 pages serving different purposes:

1. **`docs/404.html`** — Standalone root-level fallback for GitHub Pages. Copied to `/404.html` on `gh-pages` by `docs-deploy-root`. Contains JS redirect logic for legacy URLs. **NOT** part of the MkDocs build.

2. **`docs/overrides/404.html`** — MkDocs Material template override. Controls the versioned `site/404.html` rendered by MkDocs. Extends `main.html`. Must include both SEO tags (`noindex`, canonical) AND visible user-facing content (heading + link back to `/latest/`).

There must be **NO** `docs/404.md` — a Markdown 404 would be treated as content, appear in the sitemap, and create an indexable `/latest/404/` URL.

## SEO Architecture

- **`docs/overrides/main.html`** — Owns OG tags, Twitter cards, JSON-LD for all pages. Uses null-safe `page.meta` access (`page.meta and page.meta.description`). Does NOT special-case 404 behavior.
- **`docs/overrides/404.html`** — Extends `main.html`, adds `noindex/nofollow` + canonical back to `/latest/`. Must also render visible content.
- **`docs/.meta.yml`** — Default frontmatter for all pages via `meta-manager` plugin (image, description, keywords).
- Per-page `description` frontmatter in individual `.md` files overrides the default.

## robots.txt: Two Files, Different Purposes

- **`docs/robots.txt`** — Lands at `/latest/robots.txt` inside the versioned site. Crawlers ignore it (RFC 9309: only domain-root robots.txt is authoritative). Exists as a courtesy/fallback.
- **`Makefile` `ROOT_ROBOTS_TXT`** — The authoritative robots.txt deployed to domain root by `docs-deploy-root`. Allows only `/latest/`, disallows everything else, points sitemap to `/latest/sitemap.xml`.

## Deployment (`docs-deploy-root`)

The `docs-deploy-root` Makefile target deploys root assets (`404.html`, `robots.txt`, `index.html`) directly to the `gh-pages` branch via a temporary git worktree.

- Called automatically after `docs-deploy-stable` and `docs-deploy-specific-version-pre-release`
- The root `index.html` is a meta-refresh redirect to `/latest/`

## MkDocs Plugins

- `search` — site search with custom separator
- `redirects` — legacy→current URL path mapping
- `meta-manager` — applies `docs/.meta.yml` defaults to all pages
- `glightbox` — image lightbox

## Sidebar Width

Material for MkDocs hard-codes `.md-sidebar { width: 12.1rem }`. The root font-size is **20px** (not 16), so `rem` values are larger than you'd expect (12.1rem = 242px). Custom overrides live in `docs/stylesheets/general.css`.

To widen the sidebar you must override **two** things:
1. `.md-sidebar { width: ... }` — the container itself
2. `.md-sidebar .md-sidebar__inner { padding-right: 4px }` — the theme dynamically inflates `padding-right` on `.md-sidebar__inner` to absorb extra container width, keeping the nav at its original size. Pin this padding to prevent that.

## Common Mistakes to Avoid

- Do NOT create `docs/404.md` — it poisons the sitemap with an indexable `/latest/404/` URL
- Do NOT delete `docs/overrides/404.html` — it controls the versioned 404 page
- Do NOT put 404-specific SEO tags in `main.html` — that's `overrides/404.html`'s job
- Do NOT treat `docs/robots.txt` as the production robots policy — the authoritative one is `ROOT_ROBOTS_TXT` in the Makefile
- When changing URL paths, update BOTH `mkdocs.yml` `redirect_maps` AND `docs/404.html` JS rewrite rules
- Always add `mkdocs-redirects` to CI pip install when `redirect_maps` exist
