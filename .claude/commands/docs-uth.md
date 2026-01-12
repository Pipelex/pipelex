# Add a new page to the "Under the Hood" Documentation

Explain the provided feature in the docs: add a new page to @docs/under-the-hood/

Don't present the changes as "changes". Describe as if it were always like this. We are documenting the (new) current solution as the new normal.

---
Use our under-the-hood template:

Structure: Principle → Usage variants → Interfaces → Architecture (Mermaid) → Implementation → Reference tables

Approach:

- Why before how

- Exhaustive case tables (Scenario | Behavior)

- Short code snippets (5-15 lines) for every concept

- Factory-time vs runtime split when relevant

- Interfaces section (if any) covers:
  - CLI commands/flags
  - API
  - Inputs: expected types, sources, validation
  - Outputs: return types, side effects, artifacts produced

- !!! warning/info admonitions for gotchas

Tone: Terse, declarative, jargon-friendly (assumes Pydantic/Jinja2 familiarity)

Ends with: Syntax quick-ref + file→purpose table + "Next Steps" links