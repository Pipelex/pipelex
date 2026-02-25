<div align="center">
  <a href="https://www.pipelex.com/"><img src="https://raw.githubusercontent.com/Pipelex/pipelex/main/.github/assets/logo.png" alt="Pipelex Logo" width="400" style="max-width: 100%; height: auto;"></a>

  <br/>
  <br/>
  <br/>
  <h2 align="center">The Reference Runtime for Executing Methods</h2>
  <p align="center">Pipelex is the reference Python runtime for executing methods, based on the <a href="https://mthds.ai">MTHDS</a> open standard.<br/>
Write business logic, not API calls.</p>


  <div>
    <a href="https://go.pipelex.com/demo"><strong>Demo</strong></a> -
    <a href="https://docs.pipelex.com/"><strong>Documentation</strong></a> -
    <a href="https://github.com/Pipelex/pipelex/issues"><strong>Report Bug</strong></a> -
    <a href="https://github.com/Pipelex/pipelex/discussions"><strong>Feature Request</strong></a>
  </div>
  <br/>

  <p align="center">
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
    <a href="https://github.com/Pipelex/pipelex/tree/main/tests"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Pipelex/pipelex/main/.badges/tests.json" alt="Tests"></a>
    <a href="https://pypi.org/project/pipelex/"><img src="https://img.shields.io/pypi/v/pipelex?logo=pypi&logoColor=white&color=blue&style=flat-square"
     alt="PyPI – latest release"></a>
    <br/>
    <a href="https://go.pipelex.com/discord"><img src="https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
    <a href="https://www.youtube.com/@PipelexAI"><img src="https://img.shields.io/badge/YouTube-FF0000?logo=youtube&logoColor=white" alt="YouTube"></a>
    <a href="https://pipelex.com"><img src="https://img.shields.io/badge/Homepage-03bb95?logo=google-chrome&logoColor=white&style=flat" alt="Website"></a>
    <a href="https://github.com/Pipelex/pipelex-cookbook/tree/main"><img src="https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat" alt="Cookbook"></a>
    <a href="https://docs.pipelex.com/"><img src="https://img.shields.io/badge/Docs-03bb95?logo=read-the-docs&logoColor=white&style=flat" alt="Documentation"></a>
    <a href="https://docs.pipelex.com/changelog/"><img src="https://img.shields.io/badge/Changelog-03bb95?logo=git&logoColor=white&style=flat" alt="Changelog"></a>
    <br/>
    <br/>
</div>

![Pipelex Tutorial](https://raw.githubusercontent.com/Pipelex/pipelex/dev/.github/assets/pipelex-tutorial-v2.gif)


# 🚀 Quick start

## 1. Install Pipelex

```bash
pip install pipelex
pipelex init
```

## 2. Configure AI Access

To run pipelines with AI models, choose one of these options:

### Option A: Pipelex Gateway (Recommended)

Get **free credits** with a single API key for LLMs, document extraction, and image generation across all major providers (OpenAI, Anthropic, Google, Azure, and more). New models added constantly.

1. Get your API key at [app.pipelex.com](https://app.pipelex.com/)
2. Add it to your `.env` file: `PIPELEX_GATEWAY_API_KEY=your-key-here`
3. Run `pipelex init` and accept the Gateway terms of service

> **Migrating from pipelex_inference?** The old `pipelex_inference` backend is deprecated. Get your new Gateway key at [app.pipelex.com](https://app.pipelex.com/).

### Option B: Bring Your Own Keys

Use your existing API keys from OpenAI, Anthropic, Google, Mistral, etc. See [Configure AI Providers](https://docs.pipelex.com/home/5-setup/configure-ai-providers/) for setup.

### Option C: Local AI

Run models locally with Ollama, vLLM, LM Studio, or llama.cpp - no API keys required. See [Configure AI Providers](https://docs.pipelex.com/home/5-setup/configure-ai-providers/) for details.

## 3. Generate Your First Method

Create a complete AI method with a single command:

```bash
pipelex build pipe "Take a CV and Job offer in PDF, analyze if they match and generate 5 questions for the interview" --output results/cv_match.mthds
```

This command generates a production-ready `.mthds` file with domain definitions, concepts, and multiple processing steps that analyzes CV-job fit and prepares interview questions.

**cv_match.mthds**
```toml
domain = "cv_match"
description = "Matching CVs with job offers and generating interview questions"
main_pipe = "analyze_cv_job_match_and_generate_questions"

[concept.MatchAnalysis]
description = """
Analysis of alignment between a candidate and a position, including strengths, gaps, and areas requiring further exploration.
"""

[concept.MatchAnalysis.structure]
strengths = { type = "text", description = "Areas where the candidate's profile aligns well with the requirements", required = true }
gaps = { type = "text", description = "Areas where the candidate's profile does not meet the requirements or lacks evidence", required = true }
areas_to_probe = { type = "text", description = "Topics or competencies that need clarification or deeper assessment during the interview", required = true }

[concept.Question]
description = "A single interview question designed to assess a candidate."
refines = "Text"

[pipe.analyze_cv_job_match_and_generate_questions]
type = "PipeSequence"
description = """
Main pipeline that orchestrates the complete CV-job matching and interview question generation method. Takes a candidate's CV and a job offer as PDF documents, extracts their content, performs a comprehensive match analysis identifying strengths, gaps, and areas to probe, and generates exactly 5 targeted interview questions based on the analysis results.
"""
inputs = { cv_pdf = "PDF", job_offer_pdf = "PDF" }
output = "Question[5]"
steps = [
    { pipe = "extract_documents_parallel", result = "extracted_documents" },
    { pipe = "analyze_match", result = "match_analysis" },
    { pipe = "generate_interview_questions", result = "interview_questions" },
]
```

<details>
<summary><b>📄 Click to view the supporting pipes implementation</b></summary>

```toml
[pipe.extract_documents_parallel]
type = "PipeParallel"
description = """
Executes parallel extraction of text content from both the CV PDF and job offer PDF simultaneously to optimize processing time.
"""
inputs = { cv_pdf = "PDF", job_offer_pdf = "PDF" }
output = "Dynamic"
branches = [
    { pipe = "extract_cv_text", result = "cv_pages" },
    { pipe = "extract_job_offer_text", result = "job_offer_pages" },
]
add_each_output = true

[pipe.extract_cv_text]
type = "PipeExtract"
description = """
Extracts text content from the candidate's CV PDF document using OCR technology, converting all pages into machine-readable text format for subsequent analysis.
"""
inputs = { cv_pdf = "PDF" }
output = "Page[]"
model = "@default-text-from-pdf"

[pipe.extract_job_offer_text]
type = "PipeExtract"
description = """
Extracts text content from the job offer PDF document using OCR technology, converting all pages into machine-readable text format for subsequent analysis.
"""
inputs = { job_offer_pdf = "PDF" }
output = "Page[]"
model = "@default-text-from-pdf"

[pipe.analyze_match]
type = "PipeLLM"
description = """
Performs comprehensive analysis comparing the candidate's CV against the job offer requirements. Identifies and structures: (1) strengths where the candidate's profile aligns well with requirements, (2) gaps where the profile lacks evidence or doesn't meet requirements, and (3) specific areas requiring deeper exploration or clarification during the interview process.
"""
inputs = { cv_pages = "Page[]", job_offer_pages = "Page[]" }
output = "MatchAnalysis"
model = "$writing-factual"
system_prompt = """
You are an expert HR analyst and recruiter specializing in candidate-job fit assessment. Your task is to generate a structured MatchAnalysis comparing a candidate's CV against job requirements.
"""
prompt = """
Analyze the match between the candidate's CV and the job offer requirements.

Candidate CV:
@cv_pages

Job Offer:
@job_offer_pages

Perform a comprehensive comparison and provide a structured analysis.
"""

[pipe.generate_interview_questions]
type = "PipeLLM"
description = """
Generates exactly 5 targeted, relevant interview questions based on the match analysis results. Questions are designed to probe identified gaps, clarify areas of uncertainty, validate strengths, and assess competencies that require deeper evaluation to determine candidate-position fit.
"""
inputs = { match_analysis = "MatchAnalysis" }
output = "Question[5]"
model = "$testing-structured"
system_prompt = """
You are an expert HR interviewer and talent assessment specialist. Your task is to generate structured interview questions based on candidate-position match analysis.
"""
prompt = """
Based on the following match analysis between a candidate and a position, generate exactly 5 targeted interview questions.

@match_analysis

The questions should:
- Probe the identified gaps to assess if they are deal-breakers or can be mitigated
- Clarify areas that require deeper exploration
- Validate the candidate's strengths with concrete examples
- Be open-ended and behavioral when appropriate
- Help determine overall candidate-position fit

Generate exactly 5 interview questions.
"""
```
</details>


**View the pipeline flowchart:**

```mermaid
flowchart TD
 subgraph PAR["extract_documents_parallel (PipeParallel)"]
    direction LR
        EXTRACT_CV["extract_cv_text (PipeExtract)"]
        EXTRACT_JOB["extract_job_offer_text (PipeExtract)"]
  end
 subgraph MAIN["analyze_cv_job_match_and_generate_questions (PipeSequence)"]
    direction TB
        PAR
        CV_PAGES[["cv_pages: Page"]]
        JOB_PAGES[["job_offer_pages: Page"]]
        ANALYZE["analyze_match (PipeLLM)"]
        MATCH[["MatchAnalysis"]]
        GENERATE["generate_interview_questions (PipeLLM)"]
        OUT[["Question"]]
  end
    CV_IN[["cv_pdf: PDF"]] --> EXTRACT_CV
    JOB_IN[["job_offer_pdf: PDF"]] --> EXTRACT_JOB
    EXTRACT_CV --> CV_PAGES
    EXTRACT_JOB --> JOB_PAGES
    CV_PAGES --> ANALYZE
    JOB_PAGES --> ANALYZE
    ANALYZE --> MATCH
    MATCH --> GENERATE
    GENERATE --> OUT
    classDef default stroke:#1976D2,stroke-width:2px,fill:#E3F2FD,color:#0D47A1
    style EXTRACT_CV stroke:#1565C0,fill:#BBDEFB,color:#0D47A1
    style EXTRACT_JOB stroke:#1565C0,fill:#BBDEFB,color:#0D47A1
    style PAR fill:#FFF9C4,stroke:#F57C00,stroke-width:2px
    style CV_PAGES stroke:#2E7D32,fill:#C8E6C9,color:#1B5E20
    style JOB_PAGES stroke:#2E7D32,fill:#C8E6C9,color:#1B5E20
    style ANALYZE stroke:#1565C0,fill:#BBDEFB,color:#0D47A1
    style MATCH stroke:#2E7D32,fill:#C8E6C9,color:#1B5E20
    style GENERATE stroke:#1565C0,fill:#BBDEFB,color:#0D47A1
    style OUT stroke:#2E7D32,fill:#C8E6C9,color:#1B5E20
    style CV_IN stroke:#2E7D32,fill:#C8E6C9,color:#1B5E20
    style JOB_IN stroke:#2E7D32,fill:#C8E6C9,color:#1B5E20
    style MAIN fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px
```
## 4. Run Your Pipeline

**Via CLI:**

```bash
# Run with input file
pipelex run results/cv_match.mthds --inputs inputs.json
```

Create an `inputs.json` file with your PDF URLs:

```json
{
  "cv_pdf": {
    "concept": "PDF",
    "content": {
      "url": "https://pipelex-web.s3.amazonaws.com/demo/John-Doe-CV.pdf"
    }
  },
  "job_offer_pdf": {
    "concept": "PDF",
    "content": {
      "url": "https://pipelex-web.s3.amazonaws.com/demo/Job-Offer.pdf"
    }
  }
}
```

**Via Python:**

```python
import asyncio
import json
from pipelex.pipeline.runner import PipelexRunner
from pipelex.pipelex import Pipelex

async def run_pipeline():
    with open("inputs.json", encoding="utf-8") as f:
        inputs = json.load(f)

    runner = PipelexRunner()
    response = await runner.execute_pipeline(
        pipe_code="cv_match",
        inputs=inputs
    )
    pipe_output = response.pipe_output
    print(pipe_output.main_stuff_as_str)

Pipelex.make()
asyncio.run(run_pipeline())
```

<div>
  <h2 align="center">🚀 See Pipelex in Action</h2>
  
  <table align="center">
    <tr>
      <td align="center" width="50%">
        <h3>From Whiteboard to AI Method in less than 5 minutes with no hands (2025-07)</h3>
        <a href="https://go.pipelex.com/demo">
          <img src="https://go.pipelex.com/demo-thumbnail" alt="Pipelex Demo" width="100%" style="max-width: 500px; height: auto;">
        </a>
      </td>
      <td align="center" width="50%">
        <h3>The AI method that writes an AI method in 64 seconds (2025-09)</h3>
        <a href="https://go.pipelex.com/Demo-Live">
          <img src="https://d2cinlfp2qnig1.cloudfront.net/banners/pipelex_play_video_demo_live.jpg" alt="Pipelex Live Demo" width="100%" style="max-width: 500px; height: auto;">
        </a>
      </td>
    </tr>
  </table>
  
</div>

## 💡 What is Pipelex?

Pipelex is the reference Python runtime for executing **repeatable AI methods**, based on the [MTHDS](https://mthds.ai) open standard. Instead of cramming everything into one complex prompt, you break tasks into focused steps, each pipe handling one clear transformation.

Each pipe processes information using **Concepts** (typing with meaning) to ensure your pipelines make sense. The mthds language (`.mthds` files) is simple and human-readable, even for non-technical users. Each step can be structured and validated, giving you the reliability of software with the intelligence of AI.

## 📖 Next Steps

**Learn More:**
- [Design and Run Methods](https://docs.pipelex.com/home/6-build-reliable-ai-workflows/pipes/) - Complete guide with examples
- [Kick off a Method Project](https://docs.pipelex.com/home/6-build-reliable-ai-workflows/kick-off-a-methods-project/) - Deep dive into Pipelex
- [Configure AI Providers](https://docs.pipelex.com/home/5-setup/configure-ai-providers/) - Set up AI providers and models

## 🔧 IDE Extension

We **highly** recommend installing our extension for `.mthds` syntax highlighting in your IDE:

- **VS Code**: Install from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=pipelex.pipelex)
- **Cursor, Windsurf, and other VS Code forks**: Install from the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex), or search for "Pipelex" directly in your extensions tab

Running `pipelex init` will also offer to install the extension automatically if it detects your IDE.

## 📚 Examples & Cookbook

Explore real-world examples in our **Cookbook** repository:

[![GitHub](https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/tree/main)

Clone it, fork it, and experiment with production-ready pipelines for various use cases.

## 🎯 Optional Features

The package supports the following additional features:

- `anthropic`: Anthropic/Claude support for text generation
- `google`: Google models (Vertex) support for text generation
- `mistralai`: Mistral AI support for text generation and OCR
- `bedrock`: Amazon Bedrock support for text generation
- `fal`: Image generation with Black Forest Labs "FAL" service

Install all extras:

Using `pip`:
```bash
pip install "pipelex[anthropic,google,google-genai,mistralai,bedrock,fal]"
```

## Privacy & Telemetry

Pipelex supports two independent telemetry streams:

- **Gateway Telemetry**: When using Pipelex Gateway, telemetry must be enabled (tied to your hashed API key) to monitor service quality and enforce fair usage. [Learn more](https://docs.pipelex.com/home/5-setup/telemetry/#gateway-telemetry-pipelex-controlled)
- **Custom Telemetry**: User-controlled via `.pipelex/telemetry.toml` for your own observability systems (Langfuse, PostHog, OTLP). [Learn more](https://docs.pipelex.com/home/5-setup/telemetry/#custom-telemetry-user-controlled)

**We only collect technical data** (model names, token counts, latency, error rates) - never your prompts, completions, or business data. Set `DO_NOT_TRACK=1` to disable all telemetry (note: Gateway requires telemetry to function).

For more details, see the [Telemetry Documentation](https://docs.pipelex.com/home/5-setup/telemetry/) or read our [Privacy Policy](https://go.pipelex.com/privacy-policy).

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on how to get started, including development setup and testing information.

## 👥 Join the Community

Join our vibrant Discord community to connect with other developers, share your experiences, and get help with your Pipelex projects!

[![Discord](https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white)](https://go.pipelex.com/discord)

## 💬 Support

- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For questions and community discussions
- [**Documentation**](https://docs.pipelex.com/)

## ⭐ Star Us!

If you find Pipelex helpful, please consider giving us a star! It helps us reach more developers and continue improving the tool.

## 📝 License

This project is licensed under the [MIT license](LICENSE). Runtime dependencies are distributed under their own licenses via PyPI.

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
