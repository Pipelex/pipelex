### This is our viewpoint, this is why we built [Pipelex](https://pipelex.com).

Web version: https://knowhowgraph.com/

---
# Viewpoint: The Know-How Graph

Declarative, Repeatable AI Methods as Shared Infrastructure

**TL;DR**

Agents are great at solving new problems, terrible at doing the same thing twice.

We argue that repeatable AI methods should complement agents: written in a declarative language that both humans and agents can understand, reuse, and compose. These methods become tools that agents can build, invoke, and share to turn repeatable cognitive work into reliable infrastructure.

At scale, this forms a **Know-How Graph:** a network of reusable methods that become shared infrastructure.

## **Agents Are Brilliant but Hopeless at Repeatability**

When an AI agent encounters the same task for the nth time, it behaves as if it were the first: different reasoning paths, different output structures, different edge-case handling. **This is fine for novel problems, but wasteful for proven processes.**

### **Agents remember knowledge, but not know-how**

This is **the repeatability paradox**. Agents excel at understanding requirements and designing solutions. They can reason, analyze a task, break it down into logical steps, model data structures. They can remember facts and past conversations. But they can't remember the method they used to solve that same task last time. **They end up reinventing the approach every time, and someone's paying for those improv tokens.**

### We Need a Standard for Reusable Methods

The solution is to capture these methods as AI methods so agents can reuse them.

By "AI methods" we mean the actual intellectual work that wasn't automatable before LLMs: extracting structured data from unstructured documents, applying complex analyses and business rules, generating reports with reasoning. **This isn’t about API plumbing or app connectors, it’s about the actual intellectual work.**

Yet look at what's happening today: teams everywhere are hand-crafting the same methods from scratch. To extract data points from contracts and RFPs, to process expense reports, to classify documents, to screen resumes: identical problems solved in isolation, burning engineering hours.

## AI methods must be formalized

OpenAPI and MCP enable interoperability for software and agents. The remaining problem is formalizing the **methods that assemble the cognitive steps themselves:** extraction, analysis, synthesis, creativity, and decision-making, the part where understanding matters. These formalized methods must be:

- **Consistent:** same input, same output, every time.
- **Efficient:** use the right AI model for each step, large or small.
- **Transparent:** no black boxes. Domain experts can audit the logic, spot issues, suggest improvements.

The method becomes a shared artifact that humans and AI collaborate on, optimize together, and trust to run at scale.

### Current solutions are inadequate

Engineers building AI methods today are stuck with bad options.

Code frameworks like LangChain require **maintaining custom software for every method,** with business logic buried in implementation details and technical debt accumulating with each new use case.

Visual builders like Zapier, Make, or n8n excel at what they're designed for: connecting APIs and automating data flow between services. **But automation platforms are not cognitive method systems.** AI was bolted on as a feature after the fact. They weren't built for intellectual work. When you need actual understanding and multi-step reasoning, these tools quickly become unwieldy.

None of these solutions speak the language of the domain expert. None of them were built for agents to understand, modify, or generate methods from requirements. They express technical plumbing, not business logic.

At the opposite, agent SDKs and multi-agent frameworks give you flexibility but sacrifice the repeatability you need for production. **You want agents for exploration and problem-solving, but when you've found a solution that works, you need to lock it down.**

> We need a universal method language that expresses business logic, not technical plumbing.
This method language must run across platforms, models, and agent frameworks, where the method outlives any vendor or model version.
> 

## We Need a Declarative Language

AI methods should be first-class citizens of our technical infrastructure: not buried in code or trapped in platforms, but expressed in a language built for the job. The method should be an artifact you can version, diff, test, and optimize.

**We need a declarative language that states what you want, not how to compute it.** As SQL separated intent from implementation for data, we need the same for AI methods — so we can build a Know-How Graph: a reusable graph of methods that agents and humans both understand.

### The language shouldn’t need documentation: it is the documentation

Traditional programs are instructions a machine blindly executes. The machine doesn’t see your variable names or comments. With LLMs, we can write instructions the machine actually understands, enabling a new kind of human–computer collaboration.

**The abstraction level must be high enough to speak the language of each use case.** It should explicitly define concepts, include necessary explanations, and remove ambiguity. In short: self-documenting.

### Language fosters collaboration: users and agents building together

The language must be readable by everyone who matters: domain experts who know the business logic, engineers who optimize and deploy it, and crucially, AI agents that can build and refine methods autonomously.

Imagine agents that transform natural language requirements into working methods. They design each transformation step (or reuse existing ones), test against real or synthetic data, incorporate expert feedback, and iterate to improve quality while reducing costs. Once a method is built, agents can invoke it as a reliable tool whenever they need structured, predictable outputs.

> This is how agents finally remember know-how: by encoding methods into reusable methods they can build, share, and execute on demand.
> 

## The Know-How Graph: a Network of Composable Methods

**Breaking complex work into smaller tasks is a recursive, core pattern.** Each method should stand on the shoulders of others, composing like LEGO bricks to build increasingly sophisticated cognitive systems.

What emerges is a **Know-How Graph**: not just static knowledge, but executable methods that connect and build upon one another. **Unlike a knowledge graph mapping facts, this maps procedures: the actual know-how of getting cognitive work done.**

**Example:**

A recruitment method doesn't start from scratch. It composes existing methods:

- ExtractCandidateProfile (experience, education, skills…)
- ExtractJobOffer (skills, years of experience…).

These feed into your custom ScoreCard logic to produce a MatchAnalysis, which triggers either GenerateRejectionEmail or PrepareInterviewQuestions.

Each component can be assigned to different team members and validated independently by the relevant stakeholders.

> Think of a method as a proven route through the work, and the Know-How Graph as the network of all such routes.
> 

### Know-how is as shareable as knowledge

Think about the explosion of prompt sharing since 2023. All those people trading their best ChatGPT prompts on Twitter, GitHub, Reddit, LinkedIn. Now imagine that same viral knowledge sharing, but with complete, tested, composable methods instead of fragile prompts.

We’ve seen this movie: software package managers, SQL views, Docker, dbt packages. Composable standards create ecosystems where everyone’s work makes everyone else more productive. Generic methods for common tasks will spread rapidly, while companies keep their differentiating methods as competitive advantage. That's how we stop reinventing the wheel while preserving secret sauce.

The same principle applies to AI methods through the Know-How Graph: durable infrastructure that compounds value over time.

> The Know-How Graph will thrive on the open web because methods are just files: easy to publish, fork, improve, and compose.
> 

### What this unlocks

- Faster time to production (reuse existing methods + AI writes them for you)
- Lower run costs (optimize price / performance for each task)
- Better collaboration between tech and business
- Better auditability / compliance
- No vendor lock-in

## Our Solution: Pipelex

[**Pipelex**](https://github.com/Pipelex/pipelex) is our take on this language: open-source (MIT), designed for the Know-How Graph.

Each method is built from pipes: modular transformations that guarantee their output structure while applying intelligence to the content. A pipe is a knowledge transformer with a simple contract: knowledge in → knowledge out., each defined conceptually and with explicit structure and validation. The method is readable and editable by humans and agents.

Our Pipelex method builder is itself a Pipelex method. The tooling builds itself.

## Why This Can Become a Standard

Pipelex is MIT-licensed and designed for portability. Methods are files, based on TOML syntax (itself well standardized), and the outputs are validated JSON.

<!-- PRERELEASE_LINK -->
Early adopters are contributing to the [cookbook repo](https://github.com/Pipelex/pipelex-cookbook/tree/feature/Chicago), building integrations, and running methods in production. The pieces for ecosystem growth are in place: declarative spec, reference implementation, composable architecture.

Building a standard is hard. We're at v0.1.0, with versioning and backward compatibility coming next. The spec will evolve with your feedback.

## Join Us

The most valuable standards are boring infrastructure everyone relies on: SQL, HTTP, JSON. Pipelex aims to be that for AI methods.

Start with one method: extract invoice data, process applications, analyze reports… Share what works. Build on what others share.

**The future of AI needs both:** smarter agents that explore and adapt, AND reliable methods that execute proven methods at scale. One method at a time, let's build the cognitive infrastructure every organization needs.

---

© 2025 Evotis S.A.S.
Pipelex is a trademark of Evotis S.A.S.