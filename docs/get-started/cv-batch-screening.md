---
title: "CV Batch Screening, Step by Step"
description: "Screen a stack of CVs against a job offer with a multi-step Pipelex method that extracts each document, analyzes it and scores the match, run on your own machine from the CLI and from Python."
---

# CV Batch Screening, Step by Step

A production method that takes a stack of CVs and a job offer PDF, extracts and analyzes each, then scores how well each candidate matches the role. This page reads it part by part and runs it on your own machine with the Pipelex runtime, from the CLI and from Python, once you have followed [Run It Yourself](./run-it-yourself.md).

## What it demonstrates

- Typed concepts with inline structures (`CandidateProfile`, `JobRequirements`, `CandidateMatch`)
- Nested `PipeSequence` controllers, one preparing the job offer and one processing each CV
- Batching over a list of documents (`batch_over` / `batch_as`)
- Document extraction with `PipeExtract`, followed by structured analysis with `PipeLLM`

## The method: `cv_batch_screening.mthds`

### The main pipe

```toml
domain    = "cv_batch_screening"
main_pipe = "batch_analyze_cvs_for_job_offer"

[pipe.batch_analyze_cvs_for_job_offer]
type = "PipeSequence"
description = """
Main orchestrator pipe that takes a bunch of CVs and a job offer in PDF format, and analyzes how they match.
"""
inputs = { cvs = "Document[]", job_offer_pdf = "Document" }
output = "CandidateMatch[]"
steps = [
  { pipe = "prepare_job_offer", result = "job_requirements" },
  { pipe = "process_cv", batch_over = "cvs", batch_as = "cv_pdf", result = "match_analyses" },
]
```

### Concepts

```toml
[concept.CandidateProfile]
description = "A structured summary of a job candidate's professional background extracted from their CV."

[concept.CandidateProfile.structure]
skills       = { type = "text", description = "Technical and soft skills possessed by the candidate", required = true }
experience   = { type = "text", description = "Work history and professional experience", required = true }
education    = { type = "text", description = "Educational background and qualifications", required = true }
achievements = { type = "text", description = "Notable accomplishments and certifications" }

[concept.JobRequirements]
description = "A structured summary of what a job position requires from candidates."

[concept.JobRequirements.structure]
required_skills  = { type = "text", description = "Skills that are mandatory for the position", required = true }
responsibilities = { type = "text", description = "Main duties and tasks of the role", required = true }
qualifications   = { type = "text", description = "Required education, certifications, or experience levels", required = true }
nice_to_haves    = { type = "text", description = "Preferred but not mandatory qualifications" }

[concept.CandidateMatch]
description = "An evaluation of how well a candidate fits a job position."

[concept.CandidateMatch.structure]
match_score        = { type = "number", description = "Numerical score representing overall fit percentage between 0 and 100", required = true }
strengths          = { type = "text", description = "Areas where the candidate meets or exceeds requirements", required = true }
gaps               = { type = "text", description = "Areas where the candidate falls short of requirements", required = true }
overall_assessment = { type = "text", description = "Summary evaluation of the candidate's suitability", required = true }
```

### Supporting pipes

```toml
[pipe.prepare_job_offer]
type = "PipeSequence"
description = """
Extracts and analyzes the job offer PDF to produce structured job requirements.
"""
inputs = { job_offer_pdf = "Document" }
output = "JobRequirements"
steps = [
  { pipe = "extract_one_job_offer", result = "job_offer_pages" },
  { pipe = "analyze_job_requirements", result = "job_requirements" },
]

[pipe.extract_one_job_offer]
type        = "PipeExtract"
description = "Extracts text content from the job offer PDF document"
inputs      = { job_offer_pdf = "Document" }
output      = "Page[]"
model       = "@default-text-from-pdf"

[pipe.analyze_job_requirements]
type = "PipeLLM"
description = """
Parses and summarizes the job requirements from the extracted job offer content, identifying required skills, responsibilities, qualifications, and nice-to-haves
"""
inputs = { job_offer_pages = "Page" }
output = "JobRequirements"
model = "$writing-factual"
system_prompt = """
You are an expert HR analyst specializing in parsing job descriptions. Your task is to extract and summarize job requirements into a structured format.
"""
prompt = """
Analyze the following job offer content and extract the key requirements for the position.

@job_offer_pages
"""

[pipe.process_cv]
type = "PipeSequence"
description = "Processes one application"
inputs = { cv_pdf = "Document", job_requirements = "JobRequirements" }
output = "CandidateMatch"
steps = [
  { pipe = "extract_one_cv", result = "cv_pages" },
  { pipe = "analyze_one_cv", result = "candidate_profile" },
  { pipe = "analyze_match", result = "match_analysis" },
]

[pipe.extract_one_cv]
type        = "PipeExtract"
description = "Extracts text content from the CV PDF document"
inputs      = { cv_pdf = "Document" }
output      = "Page[]"
model       = "@default-text-from-pdf"

[pipe.analyze_one_cv]
type = "PipeLLM"
description = """
Parses and summarizes the candidate's professional profile from the extracted CV content, identifying skills, experience, education, and achievements
"""
inputs = { cv_pages = "Page" }
output = "CandidateProfile"
model = "$writing-factual"
system_prompt = """
You are an expert HR analyst specializing in parsing and summarizing candidate CVs. Your task is to extract and structure the candidate's professional profile into a structured format.
"""
prompt = """
Analyze the following CV content and extract the candidate's professional profile.

@cv_pages
"""

[pipe.analyze_match]
type = "PipeLLM"
description = """
Evaluates how well the candidate matches the job requirements, calculating a match score and identifying strengths and gaps
"""
inputs = { candidate_profile = "CandidateProfile", job_requirements = "JobRequirements" }
output = "CandidateMatch"
model = "$writing-factual"
system_prompt = """
You are an expert HR analyst specializing in candidate-job fit evaluation. Your task is to produce a structured match analysis comparing a candidate's profile against job requirements.
"""
prompt = """
Analyze how well the candidate matches the job requirements. Evaluate their fit by comparing their skills, experience, and qualifications against what the position demands.

@candidate_profile

@job_requirements

Provide a comprehensive match analysis including a numerical score, identified strengths, gaps, and an overall assessment.
"""
```

### Flowchart

```mermaid
flowchart LR
    %% Pipe and stuff nodes within controller subgraphs
    subgraph sg_n_8b2136e3fe["batch_analyze_cvs_for_job_offer"]
        subgraph sg_n_91d5d6dc7c["prepare_job_offer"]
            n_fde22777cb["analyze_job_requirements"]
            s_f9f703fbb4(["job_requirements<br/>JobRequirements"]):::stuff
            n_b8469c838f["extract_one_job_offer"]
            s_d998350046(["job_offer_pages<br/>Page"]):::stuff
        end
        subgraph sg_n_f8d5afb7cd["process_cv_batch"]
            subgraph sg_n_6e53e16369["process_cv"]
                n_c18aded200["analyze_match"]
                s_5c911f7e54(["match_analysis<br/>CandidateMatch"]):::stuff
                n_a7ed00ac24["analyze_one_cv"]
                s_c5ae714e89(["candidate_profile<br/>CandidateProfile"]):::stuff
                n_d24f39aa60["extract_one_cv"]
                s_427beb5195(["cv_pdf<br/>Document"]):::stuff
                s_f1f80289df(["cv_pages<br/>Page"]):::stuff
            end
            subgraph sg_n_2cfb7a32c8["process_cv"]
                n_f6a25d1769["analyze_match"]
                s_ea99eee6ed(["match_analysis<br/>CandidateMatch"]):::stuff
                n_f48b73fbee["analyze_one_cv"]
                s_e1ffee913e(["candidate_profile<br/>CandidateProfile"]):::stuff
                n_d16f2fe381["extract_one_cv"]
                s_041bb18fb4(["cv_pdf<br/>Document"]):::stuff
                s_5fbba7194a(["cv_pages<br/>Page"]):::stuff
            end
            subgraph sg_n_08a7186be9["process_cv"]
                n_937e750ea4["analyze_match"]
                s_bb41a103f0(["match_analysis<br/>CandidateMatch"]):::stuff
                n_786a2969d5["analyze_one_cv"]
                s_c47fe821d7(["candidate_profile<br/>CandidateProfile"]):::stuff
                n_38f0cfd11c["extract_one_cv"]
                s_2634ece93d(["cv_pdf<br/>Document"]):::stuff
                s_44e253b325(["cv_pages<br/>Page"]):::stuff
            end
        end
    end

    %% Pipeline input stuff nodes (no producer)
    s_9b7e74ac51(["job_offer_pdf<br/>Document"]):::stuff

    %% Data flow edges: producer -> stuff -> consumer
    n_a7ed00ac24 --> s_c5ae714e89
    n_b8469c838f --> s_d998350046
    n_f48b73fbee --> s_e1ffee913e
    n_d16f2fe381 --> s_5fbba7194a
    n_fde22777cb --> s_f9f703fbb4
    n_d24f39aa60 --> s_f1f80289df
    n_38f0cfd11c --> s_44e253b325
    n_786a2969d5 --> s_c47fe821d7
    n_c18aded200 --> s_5c911f7e54
    n_f6a25d1769 --> s_ea99eee6ed
    n_937e750ea4 --> s_bb41a103f0
    s_c5ae714e89 --> n_c18aded200
    s_9b7e74ac51 --> n_b8469c838f
    s_d998350046 --> n_fde22777cb
    s_e1ffee913e --> n_f6a25d1769
    s_427beb5195 --> n_d24f39aa60
    s_041bb18fb4 --> n_d16f2fe381
    s_2634ece93d --> n_38f0cfd11c
    s_5fbba7194a --> n_f48b73fbee
    s_f9f703fbb4 --> n_c18aded200
    s_f9f703fbb4 --> n_f6a25d1769
    s_f9f703fbb4 --> n_937e750ea4
    s_f1f80289df --> n_a7ed00ac24
    s_44e253b325 --> n_786a2969d5
    s_c47fe821d7 --> n_937e750ea4

    %% Batch edges: list-item relationships
    s_52d84618d0(["match_analyses<br/>CandidateMatch"]):::stuff
    s_5c911f7e54 -."[0]".-> s_52d84618d0
    s_ea99eee6ed -."[1]".-> s_52d84618d0
    s_bb41a103f0 -."[2]".-> s_52d84618d0

    %% Style definitions
    classDef failed fill:#ffcccc,stroke:#cc0000
    classDef stuff fill:#fff3e6,stroke:#cc6600,stroke-width:2px
    classDef controller fill:#e6f3ff,stroke:#0066cc

    %% Subgraph depth-based coloring
    style sg_n_08a7186be9 fill:#fffde6
    style sg_n_2cfb7a32c8 fill:#fffde6
    style sg_n_6e53e16369 fill:#fffde6
    style sg_n_8b2136e3fe fill:#e6f3ff
    style sg_n_91d5d6dc7c fill:#e6ffe6
    style sg_n_f8d5afb7cd fill:#e6ffe6
```

## Run the method

### From the CLI

```bash
pipelex run bundle cv_batch_screening.mthds --inputs inputs.json
```

Create an `inputs.json` file with your PDF URLs:

```json
{
  "cvs": {
    "concept": "native.Document",
    "content": [
      { "url": "https://pipelex-web.s3.amazonaws.com/demo/John-Doe-CV.pdf" },
      { "url": "inputs/Jane-Smith-CV.pdf" }
    ]
  },
  "job_offer_pdf": {
    "concept": "native.Document",
    "content": {
      "url": "https://pipelex-web.s3.amazonaws.com/demo/Job-Offer.pdf"
    }
  }
}
```

### From Python

```python
import asyncio
from pathlib import Path

from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.pipelex import Pipelex
from pipelex.pipeline.runner import PipelexMTHDSProtocol

# Generated by: `pipelex build structures cv_batch_screening.mthds`
from structures.structures import CandidateMatch


async def run_pipeline() -> list[CandidateMatch]:
    runner = PipelexMTHDSProtocol()
    response = await runner.execute(
        mthds_contents=[Path("cv_batch_screening.mthds").read_text(encoding="utf-8")],
        inputs={
            "cvs": {
                "concept": "Document",
                "content": [
                    DocumentContent(url="https://pipelex-web.s3.amazonaws.com/demo/John-Doe-CV.pdf"),
                    DocumentContent(url="inputs/Jane-Smith-CV.pdf"),
                ],
            },
            "job_offer_pdf": {
                "concept": "native.Document",
                "content": DocumentContent(url="https://pipelex-web.s3.amazonaws.com/demo/Job-Offer.pdf"),
            },
        },
    )
    pipe_output = response.pipe_output
    print(pipe_output)
    return pipe_output.main_stuff_as_items(item_type=CandidateMatch)


Pipelex.make()
asyncio.run(run_pipeline())
```
