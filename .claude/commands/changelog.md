# Update CHANGELOG.md (Unreleased)

You will be given a block of “changes” immediately after this message (pasted by the user).
Your job: update the repository changelog.

## Target file
- Prefer `CHANGELOG.md` at the repo root.
- If not found, search the repo for a changelog file (common names: CHANGELOG.md, Changelog.md, changelog.md) and use the main one.

## Rules (must follow)
1) Keep existing formatting and conventions of the file.
2) Update ONLY the `Unreleased` section:
   - If a `## [Unreleased]` (or `## Unreleased`) section exists, merge the pasted changes into it.
   - If it does not exist, create it near the top of the changelog:
     - After the main title/introduction
     - Before the first released version section
3) Merge behavior:
   - If the pasted changes already contain subsection headings like `### Added`, `### Changed`, `### Fixed`, etc., merge bullets under matching subsections in Unreleased.
   - If a needed subsection doesn’t exist under Unreleased, create it.
   - If the pasted changes do NOT include headings, classify each line into one of:
     - Added / Changed / Deprecated / Removed / Fixed / Security
     - Use best-effort classification by wording (add/introduce -> Added, fix/bug -> Fixed, remove/delete -> Removed, security/vuln -> Security, deprecate -> Deprecated, otherwise -> Changed)
   - If one of the pasted changes seems worthy of highlighting, propose to the user to do so and get their approval.
4) De-duplicate:
   - If a very similar bullet already exists in Unreleased, do not add it again.
5) Preserve order:
   - Keep the pasted changes in the order provided within each subsection.

## Output
- Make the minimal necessary edits to the changelog file.
- When done, reply with:
  - A brief summary of what you added (by subsection)
  - The exact diff or the updated Unreleased section (whichever is shorter).
