### This is our viewpoint, this is why we built [Pipelex](https://pipelex.com).

Web version: https://knowhowgraph.com/

---
# Viewpoint: The Know-How Graph

**Why AI Agents Need the MTHDS Open Standard, and What Happens When They Get It**

*By Louis Choquel, Co-founder & CTO, Pipelex*

*Originally published: November 2025*
*Updated: February 2026 — revised to reflect the emergence of Agent Skills and the evolving agent ecosystem*

---

## TL;DR

Skills gave agents reusable guidance: portable, natural-language instructions that steer behavior. But they have no types, no validation, no guaranteed output structure. That's why we built **MTHDS**: an open standard for typed, validated AI workflows with deterministic orchestration, that agents can build, execute, and share. At scale, typed methods connect to form the **Know-How Graph**: a navigable network of reusable, composable AI know-how that becomes shared infrastructure.

## Skills guide intent, not execution

Skills are a great tool to control agents: portable, natural-language instructions that guide behavior. But they're just text injected into prompts. The agent reinterprets them at every invocation: different reasoning paths, different output shapes, limited control over structure. Skills guide intent. They don't guarantee execution.

Today's most advanced harnesses like Claude Code and Codex keep agents working on complex tasks by providing context lifecycle, checkpoints, verification gates, tool execution. But deterministic orchestration and validated outputs? That still requires code. What's missing from this picture: a declarative, portable way to capture a proven method as a typed, validated artifact that runs the same way every time.

## Three Ways to Build AI Workflows Today — All Inadequate

Teams everywhere are building AI workflows to extract data from contracts, process expense reports, classify documents, screen resumes. Identical problems solved in isolation. The options they face all have serious trade-offs.

**Code** (custom Python, frameworks) gives full control: typed outputs, version control, testing. But the 100 lines that capture your actual business logic are buried in 2,000 lines of plumbing. Every workflow is bespoke, nothing composes, and the domain expert who owns the logic cannot read or iterate on it.

**Skills and prompts** are the opposite. Anyone can write them in minutes. Human-readable, progressively complex. But there is no structure, no validation, no typed outputs, no guaranteed repeatability. You ship a prompt and hope.

**Automation platforms** (Zapier, Make, n8n) are good at what they're built for: connecting APIs and automating data flow between services. But they are not cognitive workflow systems. AI was bolted on after the fact. When you need multi-step cognition (extraction, analysis, synthesis, reasoning, decision making), these tools quickly become unwieldy.

Code expresses technical plumbing, not business logic. Skills express intent without guarantees. Visual builders express data routing, not cognitive work. **What's missing is a common language between code and Skills:** structured enough to validate, conceptual enough for business experts to read, and explicit enough for agents to build and execute reliably.

## We Need a Language for AI Methods

AI workflows should be first-class citizens of our technical infrastructure: not buried in code or trapped in platforms, but expressed in a language built for the job. The method should be an artifact you can version, diff, test, and optimize.

### The Language must be Declarative and conceptual

**We need a declarative language that states what you want, not how to compute it.** SQL separated intent from implementation for data. We need the same separation for AI workflows.

But it must go further. Thanks to LLMs, machines can now grasp your intent, which opens the door to a fundamentally different way of defining workflows. The right abstraction level is the business domain itself. An `Invoice` is a declared concept with an explicit definition: what it means, what it contains, why it matters. A `NonCompeteClause` is not just "some text from a contract"; it is a concept you define once, with its purpose and characteristics spelled out in the language itself, not in a comment or a README or someone's head. That declaration is what removes ambiguity.

A method *is* the documentation, except it's also executable. A business expert reads it and sees the logic of their domain. An engineer reads it and sees something they can validate, test, and deploy. An AI agent reads it and sees something it can build, modify, and execute. One artifact, three audiences, no translation required.

Imagine agents that transform natural-language requirements into working methods. They design each transformation step (or reuse existing ones), test against real or synthetic data, incorporate expert feedback, and iterate to improve quality while reducing costs.

> This is how agents finally retain know-how: by encoding what works into conceptual methods they can build, share, and execute on demand.

### The Language must be Structured

When concepts also carry typed structures, the language gains capabilities that text-only instructions cannot support.

**Validation before runtime.** A `JobDescription` and a `CandidateProfile` might both be strings under the hood. No traditional type checker flags the swap. But feeding a candidate profile where a job description is expected is a semantic error, and in an AI workflow, the result isn't a crash. It's confident, plausible, wrong output. Concept-level typing surfaces that mistake at design time, long before you hit production.

**Discovery and composability.** Every method carries a typed signature: declared input and output concepts. That makes methods queryable, composable, and verifiable at design time. When an ecosystem of typed methods exists, something more powerful emerges.

## The Know-How Graph: A Typed Network of Composable Methods

Each method should stand on the shoulders of others, composing like LEGO bricks to build increasingly sophisticated cognitive systems.

What emerges is a **Know-How Graph**: not just static knowledge, but executable methods that connect and build upon one another. Unlike a knowledge graph that maps facts, this maps procedures: the actual know-how of getting cognitive work done.

Every method has a typed signature: declared input concepts and output concepts. This makes the graph machine-readable in a way that text-based systems cannot match.

**Type-driven discovery.** "I have a `Contract`, I need a `NonCompeteClause`" becomes a structured lookup across all published methods, matching input and output concepts. Not keyword search. Not description matching. Concept-compatible resolution across the entire ecosystem.

**Auto-composition.** When no single method bridges the gap, you find a path through the graph. One method produces a `RiskAssessment` from a `LoanApplication`. Another produces an `UnderwritingDecision` from a `RiskAssessment`. The system verifies that the two connect cleanly at design time. Compatibility is provable, not assumed. **You get pathfinding in conceptual space.**

### Know-how is as shareable as knowledge

Think about the explosion of prompt sharing since 2023 — all those people trading their best ChatGPT prompts on Twitter, GitHub, Reddit. Then Agent Skills took it further: portable capability bundles that work across agent environments, shared like dotfiles, forked like repos, with real ecosystem effects already emerging. **Now imagine that same viral sharing, but with complete, tested, composable, *typed* workflows instead of fragile prompts or unstructured instructions.**

Software package managers, SQL views, Docker images, dbt packages: composable standards create ecosystems where everyone's work makes everyone else more productive. Methods are designed for the same pattern. Common tasks get solved once and shared openly. The workflows that give your company its edge? That's your secret sauce, and it stays private. Open commons, proprietary layers on top.

## The MTHDS Open Standard

MTHDS is an open standard for defining, packaging, and distributing AI methods as typed, composable, human-readable files.

A `.mthds` file captures a method in plain TOML: declared concepts as inputs and outputs at every level, from the method itself down to each processing step, where each step can tap into the cognitive power of any AI model or run as pure deterministic logic. Orchestration is explicit: sequences, conditions, batches, parallel branches.

A `METHODS.toml` manifest turns a collection of `.mthds` files into a distributable package with dependencies, version constraints, and exports. Distribution is federated: packages live in Git repositories, registries provide discovery.

Like Skills, MTHDS files live in directories, are Git-native, and scale from personal use to enterprise deployment. Unlike Skills, they carry typed structure, validated outputs (JSON), and deterministic orchestration.

MIT-licensed. Designed for portability. The method outlives any vendor or model version.

[mthds.ai](https://mthds.ai/latest/) | [github.com/mthds-ai](https://github.com/mthds-ai)

## Pipelex: The Reference Runtime

Pipelex is the open-source reference runtime for the MTHDS standard. It reads, validates, and executes `.mthds` files, and ships as a runtime, CLI, Claude Code plugin, cookbook, and documentation.

[github.com/Pipelex/pipelex](https://github.com/Pipelex/pipelex) | [docs.pipelex.com](https://docs.pipelex.com)

## Join Us

Start with one method: extract invoice data, process applications, analyze reports. Share what works. Build on what others share. **The future of AI needs both:** Skills that give agents latitude to explore and adapt, and typed methods that guarantee execution when the output matters. They are complementary.

---

*If this Viewpoint resonates, please share it.*

*Licensed under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.*

---

**Agents + MTHDS = The Know-How Graph**

---

[MTHDS Standard](https://mthds.ai/latest/) | [Pipelex Runtime](https://github.com/Pipelex/pipelex) | [Documentation](https://docs.pipelex.com) | [Discord](https://go.pipelex.com/discord)

© 2025-2026 Evotis S.A.S. — [Pipelex](https://pipelex.com) is a trademark of Evotis S.A.S.
